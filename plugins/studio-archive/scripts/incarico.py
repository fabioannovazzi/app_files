"""Versioned assignment state beside, never in place of, the portable ledger.

The caller supplies the owning ledger module so native tools, CLI and tests use
the same identity, locking and byte-verification implementation. Semantic choice
of purpose, workflow and result belongs to Vera and the user's instruction.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

__all__ = ["Incarichi"]

SCHEMA = "vera.incarico.v1"
_FIELDS = {"purpose", "workflow_id", "continuation", "results", "conversations"}
# Public pipeline names and their documented internal engine stages.
_STAGES = {
    "quesito-legale-fiscale": {"prompt-optimizer", "deep-research-validator"},
    "fatture-xml-check": {"client-file-preparation"},
    "report-enti-locali": {"report-builder"},
    "check-entries": {"journal-sampling"},
    "new-client": {"client-file-preparation"},
    "vouching": {"journal-sampling", "check-entries"},
    "purchase-invoice-review": {"passive-invoice-audit"},
    "financial-report-builder": {"report-builder"},
    "bilancio-oic": {"bilancio-xbrl-it"},
    "avviso-intake": {"client-file-preparation"},
    "agenzia-acquisition": {"browser-automation"},
    "contenzioso-tributario": {
        "client-file-preparation",
        "prompt-optimizer",
        "deep-research-validator",
    },
}


class Incarichi:
    """Read, bind and continue one purpose through existing saved work."""

    def __init__(self, ledger: ModuleType) -> None:
        self.ledger = ledger

    def _directory(self, root: Path, engagement_id: str) -> Path:
        self.ledger.load_engagement_manifest(root, engagement_id)
        return self.ledger._engagement_root(root.resolve(), engagement_id)

    def read(self, root: Path, engagement_id: str) -> dict[str, Any]:
        """Read an assignment without writing or manufacturing a legacy workflow."""
        directory = self._directory(root, engagement_id)
        path = directory / "incarico.json"
        if not path.exists() and not path.is_symlink():
            return {
                "revision": "",
                "purpose": "",
                "workflow_id": None,
                "continuation": "",
                "results": [],
                "conversations": [],
            }
        value = self.ledger._validate_seal(
            self.ledger._read_json(path, label="incarico"), label="incarico"
        )
        required = _FIELDS | {
            "schema_version",
            "client_id",
            "engagement_id",
            "previous_revision",
            "updated_at",
            "content_sha256",
        }
        if set(value) != required or value["schema_version"] != SCHEMA:
            raise self.ledger.LedgerError("Incarico schema is invalid")
        client = self.ledger.load_client_manifest(root)
        if (value["client_id"], value["engagement_id"]) != (
            client["client_id"],
            engagement_id,
        ):
            raise self.ledger.LedgerError("Incarico belongs to another assignment")
        self._validate_fields(value)
        return {**value, "revision": value["content_sha256"]}

    def _validate_fields(self, fields: dict[str, Any]) -> None:
        text = self.ledger._text
        text(fields["purpose"], label="incarico purpose", maximum=2000)
        if fields["workflow_id"] is not None and (
            not isinstance(fields["workflow_id"], str)
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", fields["workflow_id"])
        ):
            raise self.ledger.LedgerError("Incarico workflow is invalid")
        if (
            not isinstance(fields["continuation"], str)
            or len(fields["continuation"]) > 12000
        ):
            raise self.ledger.LedgerError(
                "Continuation must be at most 12000 characters"
            )
        for field in ("results", "conversations"):
            if not isinstance(fields[field], list) or len(fields[field]) > 1000:
                raise self.ledger.LedgerError(f"Invalid incarico {field}")
        seen = set()
        for result in fields["results"]:
            if not isinstance(result, dict) or set(result) != {
                "reference",
                "label",
                "sha256",
            }:
                raise self.ledger.LedgerError("Invalid saved result declaration")
            text(result["label"], label="result label", maximum=200)
            key = self.reference_key(result["reference"])
            if (
                key in seen
                or not isinstance(result["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", result["sha256"])
            ):
                raise self.ledger.LedgerError("Duplicate result or invalid digest")
            seen.add(key)
        seen = set()
        for conversation in fields["conversations"]:
            if not isinstance(conversation, dict) or set(conversation) != {
                "host",
                "thread_id",
                "title",
                "url",
            }:
                raise self.ledger.LedgerError("Invalid conversation association")
            for key in ("host", "thread_id", "title"):
                text(conversation[key], label=key, maximum=300)
            key = (conversation["host"], conversation["thread_id"])
            if key in seen:
                raise self.ledger.LedgerError("Duplicate conversation association")
            seen.add(key)
            url = conversation["url"]
            if not isinstance(url, str) or len(url) > 2048:
                raise self.ledger.LedgerError("Invalid conversation link")
            if url:
                parsed = urlsplit(url)
                if (
                    parsed.scheme not in {"codex", "chatgpt", "https"}
                    or (
                        parsed.scheme == "https"
                        and parsed.hostname not in {"chatgpt.com", "chat.openai.com"}
                    )
                    or parsed.username
                    or parsed.password
                ):
                    raise self.ledger.LedgerError(
                        "Conversation link must belong to the chat host"
                    )
            if conversation["host"] == "codex":
                try:
                    identifier = str(UUID(conversation["thread_id"]))
                except ValueError as exc:
                    raise self.ledger.LedgerError(
                        "Use the actual native Codex thread ID"
                    ) from exc
                expected = f"codex://threads/{identifier}"
                if identifier != conversation["thread_id"] or url not in {"", expected}:
                    raise self.ledger.LedgerError(
                        "Chat link and stored conversation identity differ"
                    )

    def reference_key(self, reference: dict[str, str]) -> str:
        """Validate a document identity; never accept a browser-provided path."""
        if not isinstance(reference, dict):
            raise self.ledger.LedgerError("Invalid document reference")
        if set(reference) == {"entry_key", "revision", "format"}:
            self.ledger.deliverables().key(reference["entry_key"])
            self.ledger.deliverables().key(reference["format"])
            if type(reference["revision"]) is not int or reference["revision"] < 1:
                raise self.ledger.LedgerError("Invalid issued revision")
            return f"{reference['entry_key']}:{reference['revision']}:{reference['format']}"
        if set(reference) == {"input_id"}:
            self.ledger._identifier(
                reference["input_id"],
                label="input_id",
                pattern=self.ledger._INPUT_ID_RE,
            )
            return reference["input_id"]
        if set(reference) == {"run_id", "artifact_id"}:
            self.ledger._identifier(
                reference["run_id"], label="run_id", pattern=self.ledger._RUN_ID_RE
            )
            self.ledger._text(
                reference["artifact_id"], label="artifact_id", maximum=120
            )
            return f"{reference['run_id']}:{reference['artifact_id']}"
        raise self.ledger.LedgerError("Select an imported document or sealed result")

    def document(
        self, root: Path, engagement_id: str, reference: dict[str, str]
    ) -> dict[str, Any]:
        """Resolve and re-hash exactly one selected source or result."""
        self.reference_key(reference)
        directory = self._directory(root, engagement_id)
        if "entry_key" in reference:
            return self.ledger.deliverables().document(root, engagement_id, reference)
        if "input_id" in reference:
            receipt = self.ledger.load_input_receipt(
                root, engagement_id, reference["input_id"]
            )
            path = directory / "inputs" / receipt["input_id"] / receipt["stored_name"]
            return {
                "reference": reference,
                "name": receipt["original_name"],
                "path": str(path),
                "sha256": receipt["sha256"],
                "byte_count": receipt["byte_count"],
                "role": receipt["role"],
            }
        manifest = self.ledger.validate_run_artifacts(
            root, engagement_id, reference["run_id"]
        )
        artifact = next(
            (
                item
                for item in manifest["artifacts"]
                if item["artifact_id"] == reference["artifact_id"]
            ),
            None,
        )
        if artifact is None:
            raise self.ledger.LedgerError(
                "Selected result is not in its saved manifest"
            )
        return {
            "reference": reference,
            "name": artifact["path"],
            "path": str(
                directory / "runs" / reference["run_id"] / "outputs" / artifact["path"]
            ),
            "sha256": artifact["sha256"],
            "byte_count": artifact["byte_count"],
            "role": artifact["purpose"],
        }

    def validate_origin(self, origin: dict[str, Any]) -> None:
        """Validate portable source identity without relying on directory names."""
        if not isinstance(origin, dict) or set(origin) != {
            "client_id",
            "engagement_id",
            "revision",
            "reference",
            "sha256",
            "label",
        }:
            raise self.ledger.LedgerError("Invalid saved result origin")
        for name, pattern in (
            ("client_id", self.ledger._CLIENT_ID_RE),
            ("engagement_id", self.ledger._ENGAGEMENT_ID_RE),
            ("revision", self.ledger._SHA256_RE),
            ("sha256", self.ledger._SHA256_RE),
        ):
            self.ledger._identifier(origin[name], label=name, pattern=pattern)
        self.reference_key(origin["reference"])
        self.ledger._text(origin["label"], label="origin label", maximum=200)

    def reuse(
        self,
        root: Path,
        engagement_id: str,
        origin_root: Path,
        origin: dict[str, Any],
        role: str,
    ) -> dict[str, Any]:
        """Snapshot one explicitly declared result into another incarico.

        Both client identities are resolved by the owning Archive service.
        Provenance is retained in the receipt and every later run binding.
        """
        self.validate_origin(origin)
        if (
            self.ledger.load_client_manifest(origin_root)["client_id"]
            != origin["client_id"]
        ):
            raise self.ledger.LedgerError("Origin client identity differs")
        if (
            root.resolve() == origin_root.resolve()
            and engagement_id == origin["engagement_id"]
        ):
            raise self.ledger.LedgerError("Reuse selects a different incarico")
        document = self.document(
            origin_root, origin["engagement_id"], origin["reference"]
        )
        if "entry_key" in origin["reference"]:
            if (
                document["source_revision"] != origin["revision"]
                or document["label"] != origin["label"]
                or document["sha256"] != origin["sha256"]
            ):
                raise self.ledger.LedgerError("Selected issued result identity differs")
        else:
            current = self.read(origin_root, origin["engagement_id"])
            if current["revision"] != origin["revision"]:
                path = (
                    self._directory(origin_root, origin["engagement_id"])
                    / "incarico-history"
                    / f"{origin['revision']}.json"
                )
                current = self.ledger._validate_seal(
                    self.ledger._read_json(path, label="origin incarico revision"),
                    label="origin incarico revision",
                )
                if (
                    current["content_sha256"] != origin["revision"]
                    or current["client_id"] != origin["client_id"]
                    or current["engagement_id"] != origin["engagement_id"]
                ):
                    raise self.ledger.LedgerError("Origin revision identity differs")
            declaration = {key: origin[key] for key in ("reference", "sha256", "label")}
            if declaration not in current["results"]:
                raise self.ledger.LedgerError(
                    "Select an explicitly saved result from that revision"
                )
        return self.ledger.import_document(
            root,
            self.ledger.load_client_manifest(root)["client_id"],
            engagement_id,
            Path(document["path"]),
            role,
            expected_sha256=origin["sha256"],
            origin=origin,
        )

    def check_workflow(self, root: Path, engagement_id: str, workflow_id: str) -> None:
        """A bound assignment cannot silently become a different kind of job."""
        if self.mapping(root, engagement_id) is not None:
            raise self.ledger.LedgerError(
                "This legacy container has mapped incarichi; continue the selected mapped assignment"
            )
        current = self.read(root, engagement_id)
        owner = current["workflow_id"]
        if current["revision"] and owner is None:
            raise self.ledger.LedgerError(
                "Resolve the saved request's owning workflow before preparation"
            )
        if (
            owner
            and workflow_id != owner
            and workflow_id not in _STAGES.get(owner, set())
        ):
            raise self.ledger.LedgerError(
                "This incarico already has a different purpose/workflow; create a separate incarico and reuse its sources."
            )

    def mapping(self, root: Path, source_engagement_id: str) -> dict[str, Any] | None:
        """Read an explicit legacy mapping; never infer jobs from filenames."""
        self.ledger._identifier(
            source_engagement_id,
            label="source engagement",
            pattern=self.ledger._ENGAGEMENT_ID_RE,
        )
        path = (
            root.resolve()
            / self.ledger.LEDGER_DIRECTORY
            / "incarico-mappings"
            / f"{source_engagement_id}.json"
        )
        if not path.exists() and not path.is_symlink():
            return None
        self.ledger._ordinary_directory(path.parent, label="incarico mappings")
        value = self.ledger._validate_seal(
            self.ledger._read_json(path, label="legacy incarico mapping"),
            label="legacy incarico mapping",
        )
        if (
            set(value)
            != {
                "schema_version",
                "client_id",
                "source_engagement_id",
                "source_label",
                "targets",
                "mapped_at",
                "content_sha256",
            }
            or value["schema_version"] != "vera.incarico_mapping.v1"
            or value["client_id"] != self.ledger.load_client_manifest(root)["client_id"]
            or value["source_engagement_id"] != source_engagement_id
        ):
            raise self.ledger.LedgerError("Legacy mapping identity is invalid")
        if (
            not isinstance(value["targets"], list)
            or not 1 <= len(value["targets"]) <= 1000
        ):
            raise self.ledger.LedgerError("Legacy mapping targets are invalid")
        seen = set()
        for target in value["targets"]:
            if not isinstance(target, dict) or set(target) != {
                "engagement_id",
                "label",
                "workflow_id",
                "runs",
            }:
                raise self.ledger.LedgerError("Legacy mapping target is invalid")
            self.ledger._identifier(
                target["engagement_id"],
                label="target engagement",
                pattern=self.ledger._ENGAGEMENT_ID_RE,
            )
            if (
                target["engagement_id"] == source_engagement_id
                or not isinstance(target["runs"], list)
                or not target["runs"]
            ):
                raise self.ledger.LedgerError(
                    "Legacy mapping cannot point to itself or an empty run set"
                )
            for run in target["runs"]:
                if not isinstance(run, dict) or set(run) != {"run_id", "static_sha256"}:
                    raise self.ledger.LedgerError("Invalid mapped run")
                self.ledger._identifier(
                    run["run_id"], label="run_id", pattern=self.ledger._RUN_ID_RE
                )
                self.ledger._identifier(
                    run["static_sha256"],
                    label="run digest",
                    pattern=self.ledger._SHA256_RE,
                )
                if run["run_id"] in seen:
                    raise self.ledger.LedgerError(
                        "A legacy run cannot belong to two mapped assignments"
                    )
                seen.add(run["run_id"])
        return value

    def map_legacy(
        self, root: Path, source_engagement_id: str, targets: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Associate old executions with explicitly chosen new jobs, preserving every old byte."""
        source = self.ledger.load_engagement_manifest(root, source_engagement_id)
        if self.read(root, source_engagement_id)["workflow_id"]:
            raise self.ledger.LedgerError(
                "Legacy mapping is for an unbound historical container"
            )
        if not isinstance(targets, list) or not 1 <= len(targets) <= 1000:
            raise self.ledger.LedgerError(
                "Select explicit target incarichi and their runs"
            )
        directory = self.ledger._ordinary_directory(
            root.resolve() / self.ledger.LEDGER_DIRECTORY / "incarico-mappings",
            label="incarico mappings",
            create=True,
        )
        with self.ledger._ledger_file_lock(directory / ".mapping.lock"):
            inventory = self.ledger.inspect_runs(
                root, source_engagement_id, verify_inputs=False
            )
            if not inventory["complete"] or not inventory["runs"]:
                raise self.ledger.LedgerError(
                    "Read the complete historical run inventory before mapping"
                )
            runs = {item["run"]["run_id"]: item["run"] for item in inventory["runs"]}
            selected_runs, selected_targets, normalized = set(), set(), []
            for target in targets:
                if not isinstance(target, dict) or set(target) != {
                    "engagement_id",
                    "run_ids",
                }:
                    raise self.ledger.LedgerError(
                        "Each mapping selects a target and exact run IDs"
                    )
                eid = target["engagement_id"]
                self.ledger._identifier(
                    eid,
                    label="target engagement",
                    pattern=self.ledger._ENGAGEMENT_ID_RE,
                )
                if eid == source_engagement_id or eid in selected_targets:
                    raise self.ledger.LedgerError(
                        "Choose distinct new incarichi for the legacy jobs"
                    )
                engagement = self.ledger.load_engagement_manifest(root, eid)
                current = self.read(root, eid)
                if not current["workflow_id"]:
                    raise self.ledger.LedgerError(
                        "Establish each target's purpose and workflow before mapping"
                    )
                ids = target["run_ids"]
                if (
                    not isinstance(ids, list)
                    or not ids
                    or any(
                        not isinstance(rid, str)
                        or rid not in runs
                        or rid in selected_runs
                        for rid in ids
                    )
                    or len(ids) != len(set(ids))
                ):
                    raise self.ledger.LedgerError(
                        "Select each exact historical run only once"
                    )
                for rid in ids:
                    self.check_workflow(root, eid, runs[rid]["workflow_id"])
                selected_runs.update(ids)
                selected_targets.add(eid)
                normalized.append(
                    {
                        "engagement_id": eid,
                        "label": engagement["label"],
                        "workflow_id": current["workflow_id"],
                        "runs": [
                            {"run_id": rid, "static_sha256": runs[rid]["static_sha256"]}
                            for rid in sorted(ids)
                        ],
                    }
                )
            if selected_runs != set(runs):
                raise self.ledger.LedgerError(
                    "Map every historical run explicitly; unresolved jobs must be clarified before conversion"
                )
            normalized.sort(key=lambda item: item["engagement_id"])
            previous = self.mapping(root, source_engagement_id)
            if previous is not None:
                if previous["targets"] != normalized:
                    raise self.ledger.LedgerError(
                        "This legacy mapping already records a different selection"
                    )
                return previous
            value = self.ledger._sealed(
                {
                    "schema_version": "vera.incarico_mapping.v1",
                    "client_id": source["client_id"],
                    "source_engagement_id": source_engagement_id,
                    "source_label": source["label"],
                    "targets": normalized,
                    "mapped_at": self.ledger._now_iso(),
                }
            )
            self.ledger._write_json(directory / f"{source_engagement_id}.json", value)
            return value

    def legacy_projection(self, root: Path, engagement_id: str) -> dict[str, Any]:
        """Keep both directions of an explicit mapping visible in Archive."""
        forward, history, issues = [], [], []
        directory = root.resolve() / self.ledger.LEDGER_DIRECTORY / "incarico-mappings"
        if directory.exists() or directory.is_symlink():
            self.ledger._ordinary_directory(directory, label="incarico mappings")
            for path in sorted(directory.glob("eng_*.json")):
                try:
                    value = self.mapping(root, path.stem)
                    if value is None:
                        continue
                    if value["source_engagement_id"] == engagement_id:
                        forward.extend(value["targets"])
                    for target in value["targets"]:
                        if target["engagement_id"] == engagement_id:
                            history.append(
                                {
                                    "engagement_id": value["source_engagement_id"],
                                    "label": value["source_label"],
                                    "runs": target["runs"],
                                }
                            )
                except (self.ledger.LedgerError, OSError):
                    issues.append(
                        {"source_engagement_id": path.stem, "available": False}
                    )
        return {
            "legacy_assignments": forward,
            "historical_assignments": history,
            "mapping_issues": issues,
        }

    def begin(
        self, root: Path, engagement_id: str, workflow_id: str, purpose: str
    ) -> dict[str, Any]:
        """Bind durable work before an engine or a model starts producing drafts."""
        # Owning pipeline IDs also cover work without an Archive engine. This
        # metadata operation never authorizes engine execution.
        if self.mapping(root, engagement_id) is not None:
            raise self.ledger.LedgerError(
                "Continue one of the explicitly mapped incarichi"
            )
        current = self.read(root, engagement_id)
        if not current["workflow_id"]:
            current = self.update(
                root,
                engagement_id,
                {
                    **{key: current[key] for key in _FIELDS},
                    "workflow_id": workflow_id,
                    "purpose": current["purpose"] or purpose,
                },
                current["revision"],
            )
        self.check_workflow(root, engagement_id, workflow_id)
        directory = self.ledger._ordinary_directory(
            self._directory(root, engagement_id) / "working",
            label="incarico working area",
            create=True,
        )
        return {
            **current,
            "working_directory": str(directory),
            "drafts_are_issued": False,
        }

    def update(
        self,
        root: Path,
        engagement_id: str,
        fields: dict[str, Any],
        expected_revision: str,
    ) -> dict[str, Any]:
        """Commit one exact revision, retaining preceding revisions and all files."""
        if not isinstance(fields, dict) or set(fields) != _FIELDS:
            raise self.ledger.LedgerError("Supply the complete incarico fields")
        self._validate_fields(fields)
        directory = self._directory(root, engagement_id)
        with self.ledger._engagement_lock(root, engagement_id):
            current = self.read(root, engagement_id)
            # Exact lost-reply retries do not manufacture another revision.
            if all(current[key] == fields[key] for key in _FIELDS):
                return current
            if current["revision"] != expected_revision:
                raise self.ledger.LedgerError(
                    "Incarico changed in another chat; reload before updating"
                )
            if (
                current["workflow_id"]
                and current["workflow_id"] != fields["workflow_id"]
            ):
                raise self.ledger.LedgerError(
                    "An established incarico cannot change pipeline"
                )
            runs = self.ledger.inspect_runs(root, engagement_id, verify_inputs=False)
            allowed = {fields["workflow_id"]} | _STAGES.get(
                fields["workflow_id"], set()
            )
            if any(item["run"]["workflow_id"] not in allowed for item in runs["runs"]):
                raise self.ledger.LedgerError(
                    "Legacy engagement contains different work; map its assignments without rewriting the runs"
                )
            if not runs["complete"]:
                raise self.ledger.LedgerError(
                    "Verify unavailable legacy runs before binding this incarico"
                )
            for result in fields["results"]:
                document = self.document(root, engagement_id, result["reference"])
                if document["sha256"] != result["sha256"]:
                    raise self.ledger.LedgerError(
                        "Saved result bytes differ from the selected version"
                    )
            client = self.ledger.load_client_manifest(root)
            content = self.ledger._sealed(
                {
                    "schema_version": SCHEMA,
                    "client_id": client["client_id"],
                    "engagement_id": engagement_id,
                    "previous_revision": current["revision"],
                    "updated_at": self.ledger._now_iso(),
                    **fields,
                }
            )
            history = self.ledger._ordinary_directory(
                directory / "incarico-history", label="incarico history", create=True
            )
            if current["revision"]:
                previous = {
                    key: value for key, value in current.items() if key != "revision"
                }
                previous_path = history / f"{current['revision']}.json"
                if previous_path.exists() or previous_path.is_symlink():
                    if (
                        self.ledger._read_json(previous_path, label="incarico revision")
                        != previous
                    ):
                        raise self.ledger.LedgerError(
                            "Existing incarico history changed"
                        )
                else:
                    self.ledger._write_json(previous_path, previous)
            self.ledger._write_json(directory / "incarico.json", content)
            return {**content, "revision": content["content_sha256"]}

    def overview(self, root: Path, engagement_id: str) -> dict[str, Any]:
        """Expose saved documents even before a workflow execution exists."""
        current = self.read(root, engagement_id)
        engagement = self.ledger.load_engagement_manifest(root, engagement_id)
        inputs = self.ledger.inspect_inputs(root, engagement_id)
        publications = self.ledger.deliverables().overview(root, engagement_id)
        legacy_outputs = {
            item["legacy_input_id"]
            for entry in publications["deliverables"]
            for version in entry["versions"]
            for item in version["formats"]
            if "legacy_input_id" in item
        }
        results = []
        for result in current["results"]:
            if result["reference"].get("input_id") in legacy_outputs:
                continue
            try:
                document = self.document(root, engagement_id, result["reference"])
                available = document["sha256"] == result["sha256"]
            except (self.ledger.LedgerError, OSError):
                available = False
            results.append({**result, "available": available})
        return {
            **current,
            "fields": {key: current[key] for key in _FIELDS},
            "label": engagement["label"],
            "status": engagement["status"],
            "client_id": engagement["client_id"],
            "engagement_id": engagement_id,
            "documents": [
                {
                    **({"origin": item["origin"]} if "origin" in item else {}),
                    "reference": {"input_id": item["input_id"]},
                    "name": item["original_name"],
                    "role": item["role"],
                    "sha256": item["sha256"],
                    "byte_count": item["byte_count"],
                    "saved_at": item["imported_at"],
                }
                for item in inputs["inputs"]
                if item["input_id"] not in legacy_outputs
            ],
            "document_issues": inputs["blocked_inputs"],
            **publications,
            **self.legacy_projection(root, engagement_id),
            "legacy_output_inputs": sorted(legacy_outputs),
            "results": results,
            "conversations": [
                {
                    **item,
                    "url": item["url"]
                    or (
                        f"codex://threads/{item['thread_id']}"
                        if item["host"] == "codex"
                        else ""
                    ),
                }
                for item in current["conversations"]
            ],
        }
