"""Run selected work independently of Archive discovery, indexing and registration.

Exact hashes and idempotent requests preserve evidence and prevent duplicate
work. Document meaning, professional review and client selection are not inferred.
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import secrets
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Any


def _imports() -> None:
    component = Path(__file__).resolve().parents[1]
    for vendor in (
        component / "vendor/modules",
        component.parent / "_shared/vendor/modules",
    ):
        if (vendor / "vera_assurance").is_dir():
            sys.path.insert(0, str(vendor))
            break
    sys.path.insert(0, str(component / "scripts"))


_imports()

import client_ledger as ledger  # noqa: E402
from vera_assurance import (  # noqa: E402
    VERA_CLIENT_WORKFLOW_IDS,
    load_client_engagement_context_file,
)
from vera_assurance.serialization import (  # noqa: E402
    canonical_json_sha256,
    exclusive_file_lock,
)

__all__ = [
    "prepare_work",
    "finish_work",
    "inspect_work",
    "archive_work",
    "resume_work",
    "deliver_work",
    "main",
]

_RECORD = "pending-archive-work.json"
_SCHEMA = "vera.pending_archive_work.v1"
_OPTIONAL_ERRORS = (OSError, ValueError, ImportError, sqlite3.Error)


def _root(path: Path) -> Path:
    """Reject ambiguous ownership while allowing canonical OS temporary paths."""
    if not path.is_absolute():
        raise ValueError("Select an absolute authorized working folder")
    root = path.resolve()
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("Working folders must be outside a Git workspace")
    return root


def _read(root: Path) -> dict[str, Any]:
    value = ledger._validate_seal(
        ledger._read_json(root / _RECORD, label="pending Archive work"),
        label="pending Archive work",
    )
    if value.get("schema_version") != _SCHEMA:
        raise ValueError("Working folder is not a retained pending Archive job")
    return value


def _save(root: Path, value: Mapping[str, Any]) -> None:
    content = {key: item for key, item in value.items() if key != "content_sha256"}
    ledger._write_json(root / _RECORD, ledger._sealed(content))


def _pending(operation: str, error: BaseException | None = None) -> dict[str, Any]:
    return {
        "status": "pending",
        "operation": operation,
        "reason": type(error).__name__ if error else "archive_unavailable",
        "retry_pending": True,
    }


def _persist_status(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    try:
        _save(root, record)
        return {"status": "saved"}
    except OSError as exc:
        logging.getLogger(__name__).warning("Work status save pending: %s", exc)
        return _pending("save_work_status", exc)


def _version(workflow: str) -> str:
    components = Path(__file__).resolve().parents[2]
    component = {
        "agenzia-acquisition": "browser-automation",
        "fatture-xml-check": "client-file-preparation",
        "report-enti-locali": "report-builder",
    }.get(workflow, workflow)
    path = components / component / ".codex-plugin/plugin.json"
    if not path.is_file():
        return "unversioned"
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def _loaded(root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    return ledger.load_run(root, record["engagement_id"], record["run_id"])


def _result(root: Path, record: dict[str, Any]) -> dict[str, Any]:
    loaded = _loaded(root, record)
    try:
        from archive_core import retain_studio_run_binding

        binding = retain_studio_run_binding(
            root, record["engagement_id"], record["run_id"]
        )
    except (*_OPTIONAL_ERRORS, ledger.LedgerError) as exc:
        binding = {"status": "unavailable", "reason": type(exc).__name__}
    return {
        "work_binding": binding,
        "continuation": {
            "context_path": loaded["context_path"],
            "registration_pending": binding["status"] != "retained",
        },
        "work_folder": str(root),
        "workspace_kind": record["workspace_kind"],
        "client_identity_asserted": record["request"]["client_id"] is not None,
        "processing": record.get("processing", {"status": loaded["run"]["status"]}),
        "archive": record["archive"],
        "privacy_reporting": record.get("privacy_reporting", {"status": "not_checked"}),
        "client_engagement_path": loaded["context_path"],
        "client_engagement": loaded["context"],
        "run": loaded["run"],
        "outputs": record.get("outputs", []),
    }


def prepare_work(
    destination: Path,
    *,
    workflow_id: str,
    sources: Sequence[tuple[Path, str]],
    label: str,
    purpose: str,
    client_id: str | None = None,
) -> dict[str, Any]:
    """Prepare/start one durable job without any Archive service prerequisites.

    Without an established client ID the ledger namespace is a general working
    folder, not a claim of client onboarding or successful Archive registration.
    A changed request needs a different working folder; exact retries resume.
    """
    root = _root(destination)
    if workflow_id not in VERA_CLIENT_WORKFLOW_IDS or not sources:
        raise ValueError("Select a supported workflow and its actual input files")
    if not label.strip() or not purpose.strip():
        raise ValueError("Describe the requested work")
    selected = [(str(path.absolute()), role) for path, role in sources]
    if len(set(selected)) != len(selected):
        raise ValueError("Selected inputs contain duplicates")
    request = {
        "workflow_id": workflow_id,
        "sources": selected,
        "label": label,
        "purpose": purpose,
        "client_id": client_id,
    }
    # JSON-normalize tuples so a subsequent process compares the same request.
    request = json.loads(json.dumps(request))
    if root.exists() and not (root / _RECORD).is_file():
        raise ValueError("Choose a new working folder; existing contents are preserved")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with exclusive_file_lock(root / ".pending-work.lock"):
        if (root / _RECORD).exists():
            record = _read(root)
            if record["request"] != request:
                raise ValueError("Working folder belongs to a different request")
            if record.get("run_id"):
                loaded = _loaded(root, record)
                if loaded["run"]["status"] == "prepared":
                    ledger.start_run(root, record["engagement_id"], record["run_id"])
                return _result(root, record)
        else:
            record = {
                "schema_version": _SCHEMA,
                "request": request,
                "request_id": canonical_json_sha256(request),
                "workspace_kind": "client" if client_id else "general",
                "client_id": client_id or "client_" + secrets.token_hex(12),
                "archive": _pending("register_work"),
                "imports": [],
            }
            _save(root, record)
        ledger.create_client_manifest(root, record["client_id"])
        engagement = ledger.ensure_engagement(
            root, record["client_id"], label, idempotency_key=record["request_id"]
        )["engagement"]
        record["engagement_id"] = engagement["engagement_id"]
        _save(root, record)
        for index, (source, role) in enumerate(selected):
            if index < len(record["imports"]):
                continue
            imported = ledger.import_document(
                root, record["client_id"], record["engagement_id"], Path(source), role
            )
            record["imports"].append(imported["receipt"]["input_id"])
            _save(root, record)
        prepared = ledger.prepare_run(
            root,
            record["client_id"],
            record["engagement_id"],
            workflow_id,
            _version(workflow_id),
            input_ids=record["imports"],
            label=label,
            purpose=purpose,
            idempotency_key=record["request_id"],
        )
        record["run_id"] = prepared["run"]["run_id"]
        _save(root, record)
        started = ledger.start_run(root, record["engagement_id"], record["run_id"])
        record["privacy_reporting"] = started["reporting"]
        _persist_status(root, record)
        return _result(root, record)


def _outputs(loaded: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = Path(loaded["output_dir"])
    result = []
    for path in ledger._output_files(output):
        count, digest = ledger._stable_file_identity(path, label="saved result")
        result.append({"path": str(path), "byte_count": count, "sha256": digest})
    return result


def _archive_path(target: Path, relative: Path) -> Path:
    """Existing nested aliases must not redirect a retained-work copy."""
    path = target
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Archive destination contains a symbolic link")
    return path


def finish_work(destination: Path) -> dict[str, Any]:
    """Deliver saved results even when Archive/reporting finalization is pending."""
    root = _root(destination)
    with ExitStack() as stack:
        try:
            stack.enter_context(exclusive_file_lock(root / ".pending-work.lock"))
        except OSError as exc:
            # Delivery is a read, not a mutation of the archived job. A busy or
            # read-only bookkeeping lock cannot withhold stable saved outputs.
            record = _read(root)
            result = _result(root, record)
            outputs = _outputs(_loaded(root, record))
            if not outputs:
                raise ValueError("No saved result is available to deliver") from exc
            return {
                **result,
                "outputs": outputs,
                "processing": {
                    "status": "result_ready",
                    "finalization": _pending("finalize_work", exc),
                },
                "archive": _pending("verify_archive", exc),
                "status_record": _pending("save_work_status", exc),
            }
        return _finish_record(root, _read(root))


def _finish_record(
    root: Path, record: dict[str, Any], *, persist: bool = True
) -> dict[str, Any]:
    loaded = _loaded(root, record)
    outputs = _outputs(loaded)
    if not outputs:
        raise ValueError("No saved result is available to deliver")
    if record["archive"]["status"] == "saved" and outputs != record.get("outputs"):
        record["archive"] = _pending("archive_revised_work")
    output_root = Path(loaded["output_dir"])
    declarations = [
        {
            "artifact_id": "output_" + canonical_json_sha256(item)[:24],
            "path": Path(item["path"]).relative_to(output_root).as_posix(),
            "purpose": record["request"]["purpose"],
            "audience": "review",
            "media_type": mimetypes.guess_type(item["path"])[0]
            or "application/octet-stream",
        }
        for item in outputs
    ]
    finalization: dict[str, Any] = {"status": "completed"}
    try:
        if loaded["run"]["status"] == "completed":
            ledger.validate_run_artifacts(
                root, record["engagement_id"], record["run_id"]
            )
        else:
            finalized = ledger.finalize_run(
                root, record["engagement_id"], record["run_id"], declarations
            )
            record["privacy_reporting"] = finalized["reporting"]
            completed = ledger.complete_run(
                root, record["engagement_id"], record["run_id"]
            )
            record["privacy_reporting"] = completed["reporting"]
    except (*_OPTIONAL_ERRORS, ledger.LedgerError) as exc:
        finalization = _pending("finalize_work", exc)
    # Read current bytes after automatic report generation, without making
    # finalization or a secondary status write a condition of delivery.
    record["outputs"] = _outputs(loaded)
    record["processing"] = {"status": "result_ready", "finalization": finalization}
    if persist:
        persistence = _persist_status(root, record)
    else:
        try:
            ledger._write_json(
                Path(loaded["run_root"]) / "archive-delivery-status.json",
                {
                    "processing": record["processing"],
                    "archive": record["archive"],
                    "privacy_reporting": record.get(
                        "privacy_reporting", {"status": "not_checked"}
                    ),
                },
            )
            persistence = {"status": "saved"}
        except OSError as exc:
            persistence = _pending("save_delivery_status", exc)
    return {**_result(root, record), "status_record": persistence}


def inspect_work(destination: Path) -> dict[str, Any]:
    """Reopen saved work without discovery, registration, indexing or calculation."""
    root = _root(destination)
    record = _read(root)
    result = _result(root, record)
    result["outputs"] = _outputs(_loaded(root, record))
    return result


def _existing_work(context_path: Path, workflow_id: str) -> tuple[Path, dict[str, Any]]:
    context = load_client_engagement_context_file(
        context_path,
        expected_workflow_id=workflow_id,
        allowed_statuses=("prepared", "running", "ready_for_review", "completed"),
    )
    root = Path(context["studio_client_folder"]["client_root"])
    record: dict[str, Any] = {
        "workspace_kind": "existing",
        "client_id": context["client_id"],
        "engagement_id": context["engagement_id"],
        "run_id": context["run_id"],
        # A ledger ID identifies storage, not an asserted professional identity.
        "request": {"client_id": None, "purpose": context["purpose"]},
        "archive": {**_pending("archive_services"), "working_files_available": True},
    }
    try:
        retained = _read(root)
    except (*_OPTIONAL_ERRORS, ledger.LedgerError) as exc:
        logging.getLogger(__name__).warning("Work metadata unavailable: %s", exc)
    else:
        request = retained.get("request")
        if (
            all(
                retained.get(key) == context[key]
                for key in ("client_id", "engagement_id", "run_id")
            )
            and isinstance(request, dict)
            and request.get("workflow_id") == workflow_id
            and "client_id" in request
            and request["client_id"] in (None, context["client_id"])
        ):
            record["request"]["client_id"] = request["client_id"]
            record["workspace_kind"] = "client" if request["client_id"] else "general"
            if "privacy_reporting" in retained:
                record["privacy_reporting"] = retained["privacy_reporting"]
    return root, record


def resume_work(context_path: Path, workflow_id: str) -> dict[str, Any]:
    """Use an already-admitted run without an index, registry or private profile."""
    root, record = _existing_work(context_path, workflow_id)
    loaded = _loaded(root, record)
    if loaded["run"]["status"] == "prepared":
        started = ledger.start_run(root, record["engagement_id"], record["run_id"])
        record["privacy_reporting"] = started["reporting"]
    result = _result(root, record)
    result["outputs"] = _outputs(_loaded(root, record))
    return result


def deliver_work(context_path: Path, workflow_id: str) -> dict[str, Any]:
    """Deliver an existing run without repeating Archive discovery or preparation."""
    root, record = _existing_work(context_path, workflow_id)
    return _finish_record(root, record, persist=False)


def _archive_files(
    root: Path, record: Mapping[str, Any], loaded: Mapping[str, Any]
) -> list[Path]:
    """Copy this job's retained evidence, never a sibling engagement or run."""
    engagement = root / "Vera/engagements" / record["engagement_id"]
    files = {root / "Vera/client.json", engagement / "engagement.json"}
    directories = [Path(loaded["run_root"])]
    directories.extend(engagement / "inputs" / item for item in record["imports"])
    for directory in directories:
        ledger._ordinary_directory(directory, label="selected work evidence")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError("Selected work evidence contains a symbolic link")
            if not path.is_dir():
                files.add(path)
    return sorted(files)


def _publication_path(
    journal: Path,
    request_id: str,
    selected: Mapping[str, tuple[Path, tuple[int, str]]],
) -> str | None:
    """Identify a verified incomplete publication belonging to this exact job."""
    if not journal.exists():
        return None
    pending = ledger._validate_seal(
        ledger._read_json(journal, label="archive publication"),
        label="archive publication",
    )
    relative = pending.get("path")
    if pending.get("request_id") != request_id or relative not in selected:
        raise ValueError("Pending archival publication belongs to another request")
    _, expected = selected[relative]
    if (pending.get("byte_count"), pending.get("sha256")) != expected:
        raise ValueError("Pending archival source changed; retained both versions")
    return str(relative)


def _recover_publication(
    target: Path,
    journal: Path,
    request_id: str,
    selected: Mapping[str, tuple[Path, tuple[int, str]]],
) -> list[str]:
    """Retain interrupted exclusive-copy bytes before retrying their owned path."""
    relative = _publication_path(journal, request_id, selected)
    if relative is None:
        return []
    _, expected = selected[relative]
    path = _archive_path(target, Path(relative))
    preserved = []
    if path.exists() or path.is_symlink():
        observed = ledger._stable_file_identity(path, label="pending archive copy")
        if observed != expected:
            # A rename preserves even a later edit to the partial inode. Never
            # copy-then-delete a concurrently edited file or discard its bytes.
            evidence = _archive_path(
                target,
                Path(".pending-work-evidence") / request_id / secrets.token_hex(12),
            )
            evidence.mkdir(parents=True, mode=0o700)
            ledger._write_json(
                evidence / "receipt.json",
                {"original_path": relative, "expected_sha256": expected[1]},
            )
            path.rename(evidence / "retained-partial")
            ledger._stable_file_identity(
                evidence / "retained-partial", label="preserved partial copy"
            )
            preserved.append(str(evidence / "retained-partial"))
    journal.unlink()
    return preserved


def archive_work(destination: Path, archive_destination: Path) -> dict[str, Any]:
    """Retry exact-byte archival without executing or changing professional work.

    The destination is explicitly selected. Existing client identity must match;
    existing different bytes are never overwritten, including after a partial copy.
    """
    root, target = _root(destination), _root(archive_destination)
    if root == target or root.is_relative_to(target) or target.is_relative_to(root):
        raise ValueError("Archive destination must be separate from the working folder")
    with exclusive_file_lock(root / ".pending-work.lock"):
        record = _read(root)
        loaded = _loaded(root, record)
        outputs = _outputs(loaded)
        if record.get("processing", {}).get("status") != "result_ready":
            raise ValueError("Finish and deliver the saved work before archiving")
        if outputs != record["outputs"]:
            raise ValueError(
                "Saved outputs changed; inspect and finish the revised result"
            )
        try:
            if loaded["run"]["status"] in {"completed", "ready_for_review"}:
                ledger.validate_run_artifacts(
                    root, record["engagement_id"], record["run_id"]
                )
            selected_files = {
                path.relative_to(root).as_posix(): (
                    path,
                    ledger._stable_file_identity(path, label="retained work"),
                )
                for path in _archive_files(root, record, loaded)
            }
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            with exclusive_file_lock(target / ".pending-work.lock"):
                client_manifest = _archive_path(target, Path("Vera/client.json"))
                marker = target / ("pending-work-" + record["request_id"] + ".json")
                if (
                    not client_manifest.exists()
                    and not marker.exists()
                    and any(
                        path.name != ".pending-work.lock" for path in target.iterdir()
                    )
                ):
                    raise ValueError("Archive destination contains unowned work")
                identity = {
                    "request_id": record["request_id"],
                    "client_id": record["client_id"],
                    "engagement_id": record["engagement_id"],
                    "run_id": record["run_id"],
                    "workspace_kind": record["workspace_kind"],
                }
                if marker.exists():
                    if json.loads(marker.read_text(encoding="utf-8")) != identity:
                        raise ValueError("Archive retry belongs to another job")
                publication = target / (
                    "pending-publication-" + record["request_id"] + ".json"
                )
                pending_path = _publication_path(
                    publication, record["request_id"], selected_files
                )
                if client_manifest.exists():
                    try:
                        client = ledger.load_client_manifest(target)
                    except (ValueError, ledger.LedgerError):
                        if not marker.exists() or pending_path != "Vera/client.json":
                            raise
                    else:
                        if client["client_id"] != record["client_id"]:
                            raise ValueError(
                                "Archive destination belongs to another client"
                            )
                if not marker.exists():
                    ledger._write_json(marker, identity)
                preserved = _recover_publication(
                    target, publication, record["request_id"], selected_files
                )
                for name, (source, expected) in selected_files.items():
                    relative = Path(name)
                    path = _archive_path(target, relative)
                    if relative == Path("Vera/client.json") and path.exists():
                        # The selected client identity was verified above. Its
                        # original creation timestamp belongs to that archive.
                        continue
                    if path.exists() or path.is_symlink():
                        if (
                            ledger._stable_file_identity(path, label="archived work")
                            != expected
                        ):
                            raise ValueError(
                                "Archive contains different bytes; preserved both copies"
                            )
                        continue
                    ledger._ordinary_directory(
                        path.parent, label="archive destination", create=True
                    )
                    ledger._write_json(
                        publication,
                        ledger._sealed(
                            {
                                "request_id": record["request_id"],
                                "path": name,
                                "byte_count": expected[0],
                                "sha256": expected[1],
                            }
                        ),
                    )
                    if ledger._stable_copy(source, path, exclusive=True) != expected:
                        raise ValueError("Archive copy changed during transfer")
                    publication.unlink()
                copied = _loaded(target, record)
                if copied["run"]["static_sha256"] != loaded["run"]["static_sha256"]:
                    raise ValueError(
                        "Archived run identity differs from the saved work"
                    )
                expected_outputs = [
                    {**item, "path": Path(item["path"]).relative_to(root).as_posix()}
                    for item in outputs
                ]
                copied_outputs = [
                    {**item, "path": Path(item["path"]).relative_to(target).as_posix()}
                    for item in _outputs(copied)
                ]
                if copied_outputs != expected_outputs or _outputs(loaded) != outputs:
                    raise ValueError(
                        "Saved result changed during archiving; retry pending"
                    )
                record["archive"] = {
                    "status": "saved",
                    "destination": str(target),
                    "retry_pending": False,
                    "index_status": "not_refreshed",
                    "preserved_partial_files": preserved,
                }
        except (*_OPTIONAL_ERRORS, ledger.LedgerError) as exc:
            record["archive"] = {**_pending("archive_work", exc), "message": str(exc)}
        persistence = _persist_status(root, record)
        return {**_result(root, record), "status_record": persistence}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--workflow", required=True)
    prepare.add_argument("--label", required=True)
    prepare.add_argument("--purpose", required=True)
    prepare.add_argument("--client-id")
    for role in ("source", "journal", "support"):
        prepare.add_argument("--" + role, type=Path, action="append", default=[])
    for command in (
        prepare,
        commands.add_parser("finish"),
        commands.add_parser("status"),
    ):
        command.add_argument("--destination", type=Path, required=True)
    archive = commands.add_parser("archive")
    archive.add_argument("--destination", type=Path, required=True)
    archive.add_argument("--archive-destination", type=Path, required=True)
    for name in ("resume", "deliver"):
        command = commands.add_parser(name)
        command.add_argument("--context", type=Path, required=True)
        command.add_argument("--workflow", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare_work(
            args.destination,
            workflow_id=args.workflow,
            sources=[
                (path, role)
                for role in ("source", "journal", "support")
                for path in getattr(args, role)
            ],
            label=args.label,
            purpose=args.purpose,
            client_id=args.client_id,
        )
    elif args.command == "archive":
        result = archive_work(args.destination, args.archive_destination)
    elif args.command in {"resume", "deliver"}:
        result = {"resume": resume_work, "deliver": deliver_work}[args.command](
            args.context, args.workflow
        )
    else:
        result = {"finish": finish_work, "status": inspect_work}[args.command](
            args.destination
        )
    sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
