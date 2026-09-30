"""Durable merger case records with exact revisions and explicit local scopes.

Fixed checks protect reference integrity, access scoping and approval history.
They do not classify transactions, decide source relevance or authenticate users.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fusione_model import (
    WORK_STATES,
    CaseError,
    canonical,
    digest,
    identifier,
    text,
    validate_data,
)

__all__ = ["CaseStore", "CaseError", "reference"]
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
P1_KINDS = {"Valuation", "ExchangeModel", "BookBridge", "Deadline", "LegalDocument"}
INTERNAL_KINDS = {
    "Evidence",
    "Decision",
    "ChangeImpact",
    "Artifact",
    "ArchiveBinding",
} | P1_KINDS


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reference(record: dict[str, Any]) -> dict[str, Any]:
    """Bind a dependency to an exact case, object, revision and content hash."""
    return {key: record[key] for key in ("operation_id", "id", "version", "sha256")}


def plain_path(path: Path, *, directory: bool = False) -> Path:
    path = path.expanduser().absolute()
    if (
        path.resolve(strict=True) != path
        or (directory and not path.is_dir())
        or (not directory and not path.is_file())
    ):
        raise CaseError("Select an ordinary path without symbolic links.")
    return path


class CaseStore:
    """One local case. Actor IDs are workflow declarations, not login credentials."""

    def __init__(self, root: Path, actor: str):
        self.root = plain_path(root, directory=True)
        self.path = plain_path(self.root / "case.sqlite")
        self.actor = identifier(actor)
        with self._connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='case'").fetchone()
            if row is None:
                raise CaseError("Missing case metadata.")
            self.metadata = json.loads(row[0])
            if self.metadata["schema_version"] != 1:
                raise CaseError("Unsupported case schema.")
            self._grant(db)

    @classmethod
    def create(
        cls,
        root: Path,
        actor: str,
        operation: dict[str, Any],
        *,
        synthetic: bool = False,
    ) -> CaseStore:
        """Create a fresh case; never overwrite an existing directory."""
        identifier(actor)
        validate_data("Operation", operation)
        root = root.expanduser().absolute()
        plain_path(root.parent, directory=True)
        root.mkdir(mode=0o700)
        path = root / "case.sqlite"
        with sqlite3.connect(path) as db:
            db.executescript(
                """
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE records (id TEXT NOT NULL, version INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY (id, version));
                CREATE TABLE grants (sequence INTEGER PRIMARY KEY, actor TEXT NOT NULL, grant_json TEXT NOT NULL);
                CREATE TABLE blobs (sha256 TEXT PRIMARY KEY, content BLOB NOT NULL);
                CREATE TRIGGER immutable_record_update BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT, 'immutable revisions'); END;
                CREATE TRIGGER immutable_record_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT, 'immutable revisions'); END;
            """
            )
            metadata = {
                "schema_version": 1,
                "operation_id": "op_" + uuid.uuid4().hex,
                "synthetic": synthetic,
                "created_at": now(),
            }
            db.execute(
                "INSERT INTO metadata VALUES ('case', ?)",
                (canonical(metadata).decode(),),
            )
            grant = {
                "role": "administrator",
                "entities": [],
                "granted_by": actor,
                "recorded_at": now(),
            }
            db.execute(
                "INSERT INTO grants (actor, grant_json) VALUES (?, ?)",
                (actor, canonical(grant).decode()),
            )
        path.chmod(0o600)
        store = cls(root, actor)
        store.put(
            "operation",
            "Operation",
            operation,
            scope=[],
            dependencies=[],
            expected_version=0,
        )
        return store

    @contextmanager
    def _connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        plain_path(self.path)
        db = sqlite3.connect(f"{self.path.as_uri()}?mode=rw", uri=True, timeout=10)
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except (CaseError, OSError, ValueError, sqlite3.Error):
            db.rollback()
            raise
        finally:
            db.close()

    def _grant(self, db: sqlite3.Connection) -> dict[str, Any]:
        row = db.execute(
            "SELECT grant_json FROM grants WHERE actor=? ORDER BY sequence DESC LIMIT 1",
            (self.actor,),
        ).fetchone()
        if row is None:
            raise CaseError("Actor has no access to this case.")
        return json.loads(row[0])

    def _allow(
        self,
        db: sqlite3.Connection,
        scope: list[str],
        *,
        write: bool = False,
        admin: bool = False,
    ) -> dict[str, Any]:
        grant = self._grant(db)
        if admin and grant["role"] != "administrator":
            raise CaseError(
                "Only the case administrator can change company bindings or grants."
            )
        if write and grant["role"] == "reader":
            raise CaseError("This actor has read access only.")
        if grant["role"] != "administrator" and not set(scope) <= set(
            grant["entities"]
        ):
            raise CaseError("This actor lacks access to one or more company scopes.")
        return grant

    def grant(self, actor: str, *, role: str, entities: list[str]) -> None:
        """Record an explicit case/company permission change with its author."""
        identifier(actor)
        if role not in {"reader", "editor", "reviewer"} or not isinstance(
            entities, list
        ):
            raise CaseError(
                "Grant reader, editor or reviewer access to explicit company IDs."
            )
        with self._connect(write=True) as db:
            self._allow(db, [], admin=True)
            if actor == self.actor:
                raise CaseError("The case administrator cannot replace its own grant.")
            for entity in entities:
                if self._load(db, identifier(entity))["kind"] != "Entity":
                    raise CaseError("A grant must reference a registered company.")
            payload = {
                "role": role,
                "entities": sorted(set(entities)),
                "granted_by": self.actor,
                "recorded_at": now(),
            }
            db.execute(
                "INSERT INTO grants (actor, grant_json) VALUES (?, ?)",
                (actor, canonical(payload).decode()),
            )

    def _decode(self, raw: str) -> dict[str, Any]:
        record = json.loads(raw)
        expected = record.pop("sha256")
        if (
            digest(record) != expected
            or record["operation_id"] != self.metadata["operation_id"]
        ):
            raise CaseError("Stored record fingerprint or case binding failed.")
        record["sha256"] = expected
        return record

    def _load(
        self, db: sqlite3.Connection, object_id: str, version: int | None = None
    ) -> dict[str, Any]:
        identifier(object_id)
        if version is None:
            row = db.execute(
                "SELECT record FROM records WHERE id=? ORDER BY version DESC LIMIT 1",
                (object_id,),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT record FROM records WHERE id=? AND version=?",
                (object_id, version),
            ).fetchone()
        if row is None:
            raise CaseError("Referenced object or version does not exist in this case.")
        return self._decode(row[0])

    def _resolve(self, db: sqlite3.Connection, ref: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(ref, dict) or set(ref) != {
            "operation_id",
            "id",
            "version",
            "sha256",
        }:
            raise CaseError("A dependency must use the full exact-version reference.")
        if ref["operation_id"] != self.metadata["operation_id"]:
            raise CaseError(
                "Cross-case references require an explicit new evidence import."
            )
        if type(ref["version"]) is not int or ref["version"] < 1:
            raise CaseError("Invalid dependency version.")
        record = self._load(db, ref["id"], ref["version"])
        self._allow(db, record["scope"])
        if reference(record) != ref:
            raise CaseError("Dependency fingerprint does not match its stored content.")
        return record

    def _heads(self, db: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = db.execute(
            "SELECT record FROM records r WHERE version=(SELECT MAX(version) FROM records WHERE id=r.id) ORDER BY id"
        )
        return [self._decode(row[0]) for row in rows]

    def read(self, object_id: str, version: int | None = None) -> dict[str, Any]:
        with self._connect() as db:
            record = self._load(db, object_id, version)
            self._allow(db, record["scope"])
            return record

    def _affected(self, db: sqlite3.Connection, object_id: str) -> list[dict[str, Any]]:
        heads = self._heads(db)
        ids = {object_id}
        changed = True
        while changed:
            changed = False
            for record in heads:
                if record["kind"] == "ChangeImpact" or record["id"] in ids:
                    continue
                if any(dep["id"] in ids for dep in record["dependencies"]):
                    ids.add(record["id"])
                    changed = True
        return [
            record
            for record in heads
            if record["id"] in ids and record["id"] != object_id
        ]

    def _append(
        self,
        db: sqlite3.Connection,
        object_id: str,
        kind: str,
        data: dict[str, Any],
        *,
        scope: list[str],
        dependencies: list[dict[str, Any]],
        expected_version: int,
        work_status: str,
    ) -> dict[str, Any]:
        identifier(object_id)
        if type(expected_version) is not int or expected_version < 0:
            raise CaseError("An explicit non-negative expected_version is required.")
        if work_status not in WORK_STATES:
            raise CaseError(
                "Work status is separate from fact status and professional approval."
            )
        if work_status == "not_applicable":
            raise CaseError(
                "The helper does not infer non-applicability; record a scoped professional decision instead."
            )
        if not isinstance(scope, list) or len(scope) != len(set(scope)):
            raise CaseError("Company scope must be an explicit list of unique IDs.")
        self._allow(db, scope, write=True, admin=kind in {"Entity", "Operation"})
        validate_data(kind, data)
        row = db.execute(
            "SELECT MAX(version) FROM records WHERE id=?", (object_id,)
        ).fetchone()
        current = row[0] or 0
        if current != expected_version:
            raise CaseError(
                "Stale write: reread the current object before revising it."
            )
        if current:
            previous = self._load(db, object_id)
            if previous["kind"] != kind or previous["scope"] != sorted(scope):
                raise CaseError(
                    "An existing identity cannot change its kind or company scope."
                )
            if kind in {"Decision", "ChangeImpact"}:
                raise CaseError(
                    "Decisions and change events are immutable; append a new decision."
                )
        if kind == "Operation" and (object_id != "operation" or scope):
            raise CaseError("There is one shared operation record per case.")
        for entity in scope:
            identifier(entity)
            if kind == "Entity" and object_id == entity:
                continue
            if self._load(db, entity)["kind"] != "Entity":
                raise CaseError("Company scope must reference Entity objects.")
        if kind == "Entity":
            if scope != [object_id]:
                raise CaseError("Entity records have exactly their own company scope.")
            for root in data["source_roots"]:
                if not isinstance(root, str) or not Path(root).is_absolute():
                    raise CaseError(
                        "Company source roots must be explicit absolute paths."
                    )
                plain_path(Path(root), directory=True)
        if not isinstance(dependencies, list):
            raise CaseError("Dependencies must be an explicit list.")
        resolved = [self._resolve(db, dep) for dep in dependencies]
        if len({r["id"] for r in resolved}) != len(resolved):
            raise CaseError("Duplicate dependency identities are not permitted.")
        affected = self._affected(db, object_id) if current else []
        descendants = {r["id"] for r in affected}
        for dep in resolved:
            if dep["id"] == object_id or dep["id"] in descendants:
                raise CaseError("Dependency cycles are not permitted.")
            if not set(dep["scope"]) <= set(scope):
                raise CaseError(
                    "A record must retain every dependent company's access scope."
                )
        kinds = {r["kind"] for r in resolved}
        if (
            kind == "Fact"
            and data["fact_status"] != "unknown"
            and "Evidence" not in kinds
        ):
            raise CaseError("Known or disputed facts require acquired evidence.")
        if kind == "RuleVersion" and "SourceVersion" not in kinds:
            raise CaseError("Rules require exact source-version dependencies.")
        if (
            kind == "SourceVersion"
            and data["access_status"] == "retrieved"
            and "Evidence" not in kinds
        ):
            raise CaseError("A retrieved source requires an imported snapshot.")
        if kind == "OwnershipEdge":
            for entity in (data["holder"], data["company"]):
                if entity not in scope or not any(
                    r["id"] == entity and r["kind"] == "Entity" for r in resolved
                ):
                    raise CaseError(
                        "Ownership requires exact references and access to both companies."
                    )
        record = {
            "schema_version": 1,
            "operation_id": self.metadata["operation_id"],
            "id": object_id,
            "kind": kind,
            "version": current + 1,
            "scope": sorted(scope),
            "work_status": work_status,
            "created_at": now(),
            "author": self.actor,
            "data": data,
            "dependencies": dependencies,
        }
        record["sha256"] = digest(record)
        db.execute(
            "INSERT INTO records VALUES (?, ?, ?)",
            (object_id, current + 1, canonical(record).decode()),
        )
        if current:
            impact_scope = sorted(
                set(scope).union(*(set(r["scope"]) for r in affected))
            )
            impact = {
                "event": "input_revision",
                "previous": reference(previous),
                "replacement": reference(record),
                "affected": [reference(r) for r in affected],
                "reason": "Exact input revision changed; dependent review is required. Historical content is preserved.",
            }
            self._append_event(db, impact, impact_scope)
        return record

    def _append_event(
        self, db: sqlite3.Connection, data: dict[str, Any], scope: list[str]
    ) -> None:
        # Events may include inaccessible dependents. Retain their union scope;
        # never disclose their IDs to an actor who only changed one company.
        record = {
            "schema_version": 1,
            "operation_id": self.metadata["operation_id"],
            "id": "impact_" + uuid.uuid4().hex,
            "kind": "ChangeImpact",
            "version": 1,
            "scope": scope,
            "work_status": "review_pending",
            "created_at": now(),
            "author": self.actor,
            "data": data,
            "dependencies": [],
        }
        record["sha256"] = digest(record)
        db.execute(
            "INSERT INTO records VALUES (?, 1, ?)",
            (record["id"], canonical(record).decode()),
        )

    def put(
        self,
        object_id: str,
        kind: str,
        data: dict[str, Any],
        *,
        scope: list[str],
        dependencies: list[dict[str, Any]],
        expected_version: int,
        work_status: str = "draft",
    ) -> dict[str, Any]:
        """Append a validated revision, with optimistic concurrency and impact history."""
        if kind in INTERNAL_KINDS or (
            kind == "BranchDecision" and "engine_version" in data
        ):
            raise CaseError(
                "Use the import, artifact or approval operation for this record kind."
            )
        with self._connect(write=True) as db:
            return self._append(
                db,
                object_id,
                kind,
                data,
                scope=scope,
                dependencies=dependencies,
                expected_version=expected_version,
                work_status=work_status,
            )

    def workpaper(
        self,
        object_id: str,
        kind: str,
        request: dict[str, Any],
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        """Derive an immutable P1 workpaper from exact inputs in one transaction."""
        from fusione_p1 import derive, selected_references

        if kind not in P1_KINDS | {"BranchDecision"}:
            raise CaseError("Unknown P1 workpaper kind.")
        with self._connect(write=True) as db:
            refs = selected_references(request)
            operation = self._load(db, "operation")
            refs[operation["id"]] = reference(operation)
            records = {key: self._resolve(db, ref) for key, ref in refs.items()}
            scope = sorted(set().union(*(set(r["scope"]) for r in records.values())))
            self._allow(db, scope, write=True)
            issues = sorted(
                set(
                    issue
                    for r in records.values()
                    for issue in self._base_issues(db, r)
                )
            )
            result = None
            if not issues:
                result, issues = derive(kind, request, records)
            data = {
                "engine_version": "fusione.p1.v1",
                "request": request,
                "result": result,
                "issues": issues,
            }
            return self._append(
                db,
                object_id,
                kind,
                data,
                scope=scope,
                dependencies=list(refs.values()),
                expected_version=expected_version,
                work_status="missing_evidence" if issues else "review_pending",
            )

    def _document(self, path: Path) -> bytes:
        source = plain_path(path)
        before = source.stat()
        if before.st_size > MAX_DOCUMENT_BYTES:
            raise CaseError("Document exceeds the 20 MiB import limit.")
        content = source.read_bytes()
        after = source.stat()
        if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_mtime_ns,
            after.st_size,
        ) or len(content) != after.st_size:
            raise CaseError("The selected file changed during import.")
        return content

    def import_evidence(
        self,
        object_id: str,
        entity_id: str,
        source: Path,
        *,
        locator: str,
        description: str,
        expected_version: int = 0,
    ) -> dict[str, Any]:
        """Copy one explicitly selected file into this case, preserving its bytes."""
        text(locator, "page/row/document locator")
        text(description, "evidence description")
        with self._connect(write=True) as db:
            self._allow(db, [entity_id], write=True)
            entity = self._load(db, entity_id)
            if entity["kind"] != "Entity":
                raise CaseError("Evidence must be bound to a registered company.")
            source = plain_path(source)
            roots = [
                plain_path(Path(p), directory=True)
                for p in entity["data"]["source_roots"]
            ]
            if not any(source.is_relative_to(root) for root in roots):
                raise CaseError(
                    "Import is outside this company's explicitly permitted directories."
                )
            content = self._document(source)
            sha256 = hashlib.sha256(content).hexdigest()
            db.execute("INSERT OR IGNORE INTO blobs VALUES (?, ?)", (sha256, content))
            data = {
                "description": description,
                "locator": locator,
                "source_path": str(source),
                "filename": source.name,
                "sha256": sha256,
                "byte_count": len(content),
                "imported_by": self.actor,
            }
            return self._append(
                db,
                object_id,
                "Evidence",
                data,
                scope=[entity_id],
                dependencies=[reference(entity)],
                expected_version=expected_version,
                work_status="review_pending",
            )

    def bind_archive(
        self,
        object_id: str,
        entity_id: str,
        client_root: Path,
        client_id: str,
        engagement_id: str,
        *,
        expected_version: int = 0,
    ) -> dict[str, Any]:
        """Bind one declared company to an exact existing Studio Archive engagement."""
        from fusione_archive import binding_data

        with self._connect(write=True) as db:
            self._allow(db, [entity_id], write=True, admin=True)
            entity = self._load(db, entity_id)
            if entity["kind"] != "Entity":
                raise CaseError("Archive binding requires a registered company.")
            root = plain_path(client_root, directory=True)
            if not any(
                root.is_relative_to(plain_path(Path(p), directory=True))
                for p in entity["data"]["source_roots"]
            ):
                raise CaseError(
                    "Archive root is outside this company's selected source roots."
                )
            data = binding_data(entity_id, root, client_id, engagement_id)
            for record in self._heads(db):
                if record["kind"] == "ArchiveBinding" and record["id"] != object_id:
                    other = record["data"]
                    if (
                        other["client_id"] == client_id
                        and other["entity_id"] != entity_id
                    ):
                        raise CaseError(
                            "One stable archive client cannot represent two companies in this case."
                        )
            return self._append(
                db,
                object_id,
                "ArchiveBinding",
                data,
                scope=[entity_id],
                dependencies=[reference(entity)],
                expected_version=expected_version,
                work_status="review_pending",
            )

    def import_archive(
        self,
        object_id: str,
        binding: dict[str, Any],
        input_id: str,
        *,
        locator: str,
        description: str,
        expected_version: int = 0,
    ) -> dict[str, Any]:
        """Snapshot one verified receipt, preserving its client/engagement provenance."""
        from fusione_archive import selected_receipt

        text(locator, "evidence locator")
        text(description, "evidence description")
        with self._connect(write=True) as db:
            bound = self._resolve(db, binding)
            if bound["kind"] != "ArchiveBinding" or self._base_issues(db, bound):
                raise CaseError("Use a current verified archive binding.")
            self._allow(db, bound["scope"], write=True)
            receipt = selected_receipt(bound["data"], input_id)
            source = plain_path(Path(receipt["path"]))
            content = self._document(source)
            sha256 = hashlib.sha256(content).hexdigest()
            if sha256 != receipt["sha256"] or len(content) != receipt["byte_count"]:
                raise CaseError("Archive bytes changed during import.")
            db.execute("INSERT OR IGNORE INTO blobs VALUES (?, ?)", (sha256, content))
            data = {
                "description": description,
                "locator": locator,
                "source_path": str(source),
                "filename": source.name,
                "sha256": sha256,
                "byte_count": len(content),
                "imported_by": self.actor,
                "archive_receipt": {
                    key: receipt[key]
                    for key in (
                        "client_id",
                        "engagement_id",
                        "input_id",
                        "content_sha256",
                        "sha256",
                        "byte_count",
                        "relative_path",
                        "receipt_relative_path",
                    )
                },
            }
            return self._append(
                db,
                object_id,
                "Evidence",
                data,
                scope=bound["scope"],
                dependencies=[binding],
                expected_version=expected_version,
                work_status="review_pending",
            )

    def artifact(
        self,
        object_id: str,
        source: Path,
        *,
        scope: list[str],
        dependencies: list[dict[str, Any]],
        recipient: str,
        expected_version: int = 0,
    ) -> dict[str, Any]:
        """Preserve a local draft's bytes and input versions, without claiming filing."""
        text(recipient, "recipient")
        with self._connect(write=True) as db:
            self._allow(db, scope, write=True)
            source = plain_path(source)
            if not source.is_relative_to(self.root / "drafts"):
                raise CaseError(
                    "Register artifacts only from this case's drafts directory."
                )
            content = self._document(source)
            sha256 = hashlib.sha256(content).hexdigest()
            db.execute("INSERT OR IGNORE INTO blobs VALUES (?, ?)", (sha256, content))
            data = {
                "relative_path": source.relative_to(self.root).as_posix(),
                "sha256": sha256,
                "byte_count": len(content),
                "recipient": recipient,
                "signature_status": "not_verified",
                "filing_status": "not_verified",
            }
            return self._append(
                db,
                object_id,
                "Artifact",
                data,
                scope=scope,
                dependencies=dependencies,
                expected_version=expected_version,
                work_status="review_pending",
            )

    def _base_issues(
        self,
        db: sqlite3.Connection,
        record: dict[str, Any],
        seen: set[tuple[str, int]] | None = None,
    ) -> list[str]:
        seen = set() if seen is None else seen
        key = (record["id"], record["version"])
        if key in seen:
            return []
        seen.add(key)
        issues = []
        if reference(self._load(db, record["id"])) != reference(record):
            issues.append(f"stale_version:{record['id']}")
        kind, data = record["kind"], record["data"]
        if record["work_status"] == "missing_evidence":
            issues.append(f"missing_evidence:{record['id']}")
        if kind == "Fact" and data["fact_status"] != "known":
            issues.append(f"{data['fact_status']}:{record['id']}")
        if kind == "SourceVersion" and data["access_status"] != "retrieved":
            issues.append(f"source_{data['access_status']}:{record['id']}")
        if kind == "RuleVersion" and data["review_status"] in {
            "superseded",
            "withdrawn",
        }:
            issues.append(f"rule_{data['review_status']}:{record['id']}")
        if kind == "BranchDecision" and "engine_version" not in data:
            issues.append(f"unsupported_branch:{record['id']}")
        if kind in P1_KINDS or (kind == "BranchDecision" and "engine_version" in data):
            issues.extend(f"p1:{record['id']}:{issue}" for issue in data["issues"])
            operation = self._load(db, "operation")
            planned = operation["data"]["planned_date"]
            if planned is None:
                issues.append(f"planned_date_missing:{record['id']}")
            for dep in record["dependencies"]:
                source = self._resolve(db, dep)
                if source["kind"] == "RuleVersion" and planned is not None:
                    start = source["data"]["applicable_from"]
                    end = source["data"]["applicable_to"]
                    if (
                        start is None
                        or planned < start
                        or (end is not None and planned > end)
                    ):
                        issues.append(f"rule_outside_declared_period:{source['id']}")
        if kind in {"Evidence", "Artifact"}:
            blob = db.execute(
                "SELECT content FROM blobs WHERE sha256=?", (data["sha256"],)
            ).fetchone()
            if blob is None or hashlib.sha256(blob[0]).hexdigest() != data["sha256"]:
                issues.append(f"blob_integrity:{record['id']}")
        for dep in record["dependencies"]:
            issues.extend(self._base_issues(db, self._resolve(db, dep), seen))
        return sorted(set(issues))

    def _rule_issues(
        self,
        db: sqlite3.Connection,
        record: dict[str, Any],
        seen: set[tuple[str, int]] | None = None,
    ) -> list[str]:
        seen = set() if seen is None else seen
        issues = []
        for dep in record["dependencies"]:
            child = self._resolve(db, dep)
            key = (child["id"], child["version"])
            if key in seen:
                continue
            seen.add(key)
            requires_review = (
                child["kind"] == "RuleVersion"
                or (
                    child["kind"] == "BranchDecision"
                    and "engine_version" in child["data"]
                )
                or (
                    record["kind"] in {"LegalDocument", "Artifact"}
                    and child["kind"] in P1_KINDS
                )
            )
            if requires_review and not self._approval_ids(db, child):
                issues.append(
                    f"rule_unapproved:{child['id']}"
                    if child["kind"] == "RuleVersion"
                    else f"input_unapproved:{child['id']}"
                )
            issues.extend(self._rule_issues(db, child, seen))
        return sorted(set(issues))

    def _approval_ids(
        self, db: sqlite3.Connection, record: dict[str, Any]
    ) -> list[str]:
        if self._base_issues(db, record) or self._rule_issues(db, record):
            return []
        return [
            r["id"]
            for r in self._heads(db)
            if r["kind"] == "Decision" and r["data"]["target"] == reference(record)
        ]

    def approve(
        self,
        object_id: str,
        target: dict[str, Any],
        *,
        professional_role: str,
        scope_text: str,
        confirmation: str,
    ) -> dict[str, Any]:
        """Record an explicit professional confirmation of exact reviewed content."""
        for label, value in (
            ("professional role", professional_role),
            ("approval scope", scope_text),
            ("confirmation evidence", confirmation),
        ):
            text(value, label)
        with self._connect(write=True) as db:
            record = self._resolve(db, target)
            grant = self._allow(db, record["scope"], write=True)
            if grant["role"] not in {"reviewer", "administrator"}:
                raise CaseError("An editor cannot record a professional approval.")
            if record["kind"] in {"Decision", "ChangeImpact"} or (
                record["kind"] == "BranchDecision"
                and "engine_version" not in record["data"]
            ):
                raise CaseError("This record is not an approvable deliverable.")
            issues = self._base_issues(db, record) + self._rule_issues(db, record)
            if issues:
                raise CaseError("Approval blocked: " + ", ".join(sorted(set(issues))))
            if record["kind"] == "RuleVersion":
                data = record["data"]
                if (
                    data["review_status"] != "professional_review_pending"
                    or not data["test_refs"]
                    or data["applicable_from"] is None
                ):
                    raise CaseError(
                        "A rule requires pending professional review, explicit applicability and test references."
                    )
            data = {
                "target": target,
                "approved_content": record["data"],
                "professional_role": professional_role,
                "scope_text": scope_text,
                "confirmation": confirmation,
                "approved_by": self.actor,
                "approved_at": now(),
                "meaning": "recorded professional confirmation; not identity, signature or legal certification",
            }
            return self._append(
                db,
                object_id,
                "Decision",
                data,
                scope=record["scope"],
                dependencies=[target],
                expected_version=0,
                work_status="review_pending",
            )

    def status(self, object_id: str) -> dict[str, Any]:
        with self._connect() as db:
            record = self._load(db, object_id)
            self._allow(db, record["scope"])
            return self._status(db, record)

    def _status(self, db: sqlite3.Connection, record: dict[str, Any]) -> dict[str, Any]:
        issues = sorted(
            set(self._base_issues(db, record) + self._rule_issues(db, record))
        )
        approvals = self._approval_ids(db, record) if not issues else []
        state = (
            "needs_review"
            if issues
            else ("approved_for_defined_scope" if approvals else "unapproved")
        )
        return {
            "reference": reference(record),
            "work_status": record["work_status"],
            "review_state": state,
            "issues": issues,
            "approval_ids": approvals,
        }

    def report(self) -> dict[str, Any]:
        """Return only records whose full inherited company scope is accessible."""
        with self._connect() as db:
            grant = self._grant(db)
            visible = [
                r
                for r in self._heads(db)
                if grant["role"] == "administrator"
                or set(r["scope"]) <= set(grant["entities"])
            ]
            records = [{"record": r, "status": self._status(db, r)} for r in visible]
            history = []
            for record in visible:
                rows = db.execute(
                    "SELECT record FROM records WHERE id=? ORDER BY version",
                    (record["id"],),
                )
                history.extend(self._decode(row[0]) for row in rows)
            return {
                "schema_version": 1,
                "operation_id": self.metadata["operation_id"],
                "synthetic": self.metadata["synthetic"],
                "actor": self.actor,
                "generated_at": now(),
                "scope": "Versioned merger case; P1 workpapers support two declared domestic OIC incorporation branches under recorded professional review. No signature, filing or legal certification.",
                "records": records,
                "history": history,
                "execution_evidence": {
                    "structural_validation": "performed on each accepted write",
                    "legal_validation": "not_run",
                    "numeric_merger_tests": "not_run",
                    "professional_case_acceptance": "not_run",
                },
            }

    def document_bytes(self, object_id: str, version: int | None = None) -> bytes:
        """Read a preserved document only after validating this actor's company scope."""
        with self._connect() as db:
            record = self._load(db, object_id, version)
            self._allow(db, record["scope"])
            if record["kind"] not in {"Evidence", "Artifact"}:
                raise CaseError("This record has no preserved document.")
            row = db.execute(
                "SELECT content FROM blobs WHERE sha256=?", (record["data"]["sha256"],)
            ).fetchone()
            if (
                row is None
                or hashlib.sha256(row[0]).hexdigest() != record["data"]["sha256"]
            ):
                raise CaseError("Preserved document integrity check failed.")
            return row[0]
