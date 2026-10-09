"""Scoped native intake and durable supervised passive-invoice job lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from native_bank_preparation import file_hash
from native_passive_audit import job_population, ordinary

__all__ = ["dispatch", "read_prepared", "lease", "lease_alive", "engine"]

TERMINAL = {"completed", "failed", "awaiting_semantic_review", "refused"}
SOURCE_ROLES = {
    "invoices",
    "ledger",
    "ledger_mapping",
    "history",
    "chart",
    "worker_selection",
}
FIELD_KEYS = {"choices", "controls", "operator_ref", "decision_basis"}


def engine(root: Path, request: dict) -> dict:
    """Call only the fixed isolated module; never run a worker in the short bridge."""
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_passive_audit_bridge.py")),
            str(root),
        ],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if completed.returncode:
        raise ValueError(
            completed.stderr.strip().splitlines()[-1]
            or "Passive-invoice producer refused"
        )
    return json.loads(completed.stdout)


@contextmanager
def lease(path: Path, *, create: bool = False) -> Iterator[None]:
    """OS locks establish live ownership and release after process death, unlike a marker."""
    if create and not path.exists():
        with path.open("xb") as stream:
            stream.write(b"1")
        path.chmod(0o600)
    ordinary(path, 32)
    with path.open("r+b") as stream:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def lease_alive(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with lease(path):
            return False
    except BlockingIOError:
        return True
    except OSError as exc:
        # Windows reports a locked byte range as EACCES; other errors are unknown.
        if os.name == "nt" and exc.errno == 13:
            return True
        raise


def scoped(binding: dict) -> list:
    return [
        os.environ["VERA_WORKSPACE_ACTOR_ID"],
        os.environ["VERA_WORKSPACE_TENANT_ID"],
        *[binding[key] for key in ("client_id", "engagement_id", "run_id")],
    ]


def read_record(path: Path, api: Any) -> dict | None:
    if not path.exists():
        return None
    value = api.read_json(path)
    if value.get("record_sha256") != api.digest(
        {key: row for key, row in value.items() if key != "record_sha256"}
    ):
        raise ValueError("Passive-invoice native record changed")
    return value


def save_record(path: Path, value: dict, api: Any) -> dict:
    value = {key: row for key, row in value.items() if key != "record_sha256"}
    value["record_sha256"] = api.digest(value)
    api.atomic_json(path, value)
    path.chmod(0o600)
    return value


def current(root: Path, binding: dict, loaded: dict, api: Any) -> dict:
    if (
        binding["workflow_id"] != "passive-invoice-audit"
        or root.name != "passive-invoice-audit"
    ):
        raise PermissionError("Passive-invoice service belongs to another workflow")
    output = Path(loaded["output_dir"])
    private = api.ui_state_directory(output, create=False)
    state = read_record(private / "passive-state.json", api)
    if state and state["run_scope"] != [
        binding[key] for key in ("client_id", "engagement_id", "run_id")
    ]:
        raise PermissionError("Invoice job belongs to another client or run")
    if state:
        review_ref = state.get("qualification_ref", "")
        if not re.fullmatch(r"[0-9a-f]{64}", review_ref):
            raise ValueError("Missing exact invoice qualification reference")
        reviewed = read_record(
            private / ("passive-qualification-" + review_ref + ".json"), api
        )
        if (
            reviewed is None
            or api.digest(
                {key: row for key, row in reviewed.items() if key != "record_sha256"}
            )
            != review_ref
            or any(
                reviewed.get(key) != state.get(key)
                for key in (
                    "run_scope",
                    "recipe",
                    "job_ref",
                    "qualification",
                    "operator_review",
                )
            )
        ):
            raise ValueError("Invoice intake differs from its immutable qualification")
    operation = None
    live = False
    if state and state.get("operation_ref"):
        identity = state["operation_ref"]
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ValueError("Invalid invoice operation reference")
        operation = read_record(
            private / ("passive-operation-" + identity + ".json"), api
        )
        if (
            operation is None
            or operation["operation_ref"] != identity
            or operation["run_scope"] != state["run_scope"]
        ):
            raise ValueError("Invoice operation receipt is missing or foreign")
        live = lease_alive(private / ("passive-lease-" + identity + ".lock"))
    info = engine(root, {"operation": "info"})
    implementation = api.digest(
        [
            info["implementation"],
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_passive_supervisor.py")),
        ]
    )
    unsettled = bool(operation and (live or operation["status"] not in TERMINAL))
    # The worker owns a mutable capsule/WAL namespace. Status does not inspect
    # capsule contents or claim an authoritative output snapshot while unsettled.
    population = operation["population"] if unsettled else job_population(output)
    revision = api.digest(
        [
            loaded["run"],
            loaded["input_manifest"],
            state,
            operation,
            population,
            implementation,
        ]
    )
    return {
        "private": private,
        "state": state,
        "operation": operation,
        "live": live,
        "unsettled": unsettled,
        "implementation": implementation,
        "population": population,
        "revision": revision,
        "runtime": info["runtime"],
    }


def fields(value: Any, inputs: dict) -> dict:
    """Validate unfinished UI shape/IDs only; source meaning remains user/model-led."""
    if (
        not isinstance(value, dict)
        or set(value) - FIELD_KEYS
        or len(json.dumps(value).encode()) > 800_000
    ):
        raise ValueError("Invalid passive-invoice draft fields")
    choices = value.get("choices", {})
    if not isinstance(choices, dict) or any(
        identity not in inputs or role not in SOURCE_ROLES
        for identity, role in choices.items()
    ):
        raise ValueError("Draft source roles are outside the exact run")
    controls = value.get("controls", {})
    if (
        not isinstance(controls, dict)
        or set(controls)
        - {
            "ledger_sheet",
            "chunk_size",
            "concurrency",
            "max_retries",
            "reasoning_effort",
            "amount_tolerance",
        }
        or any(
            not isinstance(item, str) or len(item) > 200 for item in controls.values()
        )
    ):
        raise ValueError("Invalid unfinished execution controls")
    for key in ("operator_ref", "decision_basis"):
        if key in value and (not isinstance(value[key], str) or len(value[key]) > 4000):
            raise ValueError("Invalid unfinished operator attribution")
    return value


def recipe(value: dict) -> dict:
    chosen = value.get("choices", {})
    roles: dict = {
        "invoices": [
            identity for identity, role in chosen.items() if role == "invoices"
        ]
    }
    for role in SOURCE_ROLES - {"invoices"}:
        identities = [
            identity for identity, selected in chosen.items() if selected == role
        ]
        if len(identities) > 1:
            raise ValueError("Choose only one source for each non-invoice role")
        if identities:
            roles[role] = identities[0]
    controls = dict(value.get("controls", {}))
    if set(controls) != {
        "ledger_sheet",
        "chunk_size",
        "concurrency",
        "max_retries",
        "reasoning_effort",
        "amount_tolerance",
    }:
        raise ValueError("Review all execution controls")
    for key in ("chunk_size", "concurrency", "max_retries"):
        if not re.fullmatch(r"\d{1,3}", controls[key]):
            raise ValueError("Execution counts must be explicit integers")
        controls[key] = int(controls[key])
    controls["ledger_sheet"] = controls["ledger_sheet"] or None
    return {"inputs": roles, "controls": controls}


def draft_path(current: dict, binding: dict, api: Any) -> Path:
    return current["private"] / (
        "passive-draft-" + api.digest(scoped(binding)) + ".json"
    )


def draft(current: dict, binding: dict, api: Any) -> dict:
    value = read_record(draft_path(current, binding, api), api)
    if value and value["scope"] != scoped(binding):
        raise PermissionError("Invoice draft belongs to another actor or tenant")
    stale = bool(value and value["revision"] != current["revision"])
    return {
        "fields": value["fields"] if value and not stale else {},
        "draft_revision": value["record_sha256"] if value else "",
        "exists": bool(value),
        "stale": stale,
    }


def setup(root: Path, binding: dict, loaded: dict, args: dict, api: Any) -> dict:
    value = current(root, binding, loaded, api)
    offset = args.get("offset", 0)
    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid source page")
    rows = [
        {
            "id": row["binding_id"],
            "title": Path(row["path"]).name,
            "role": row["role"],
            "sha256": row["sha256"],
        }
        for row in loaded["context"]["input_bindings"]
    ]
    state, operation = value["state"], value["operation"]
    writable = (
        loaded["run"]["status"] == "running"
        and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        and not value["unsettled"]
    )
    return {
        "work_ref": binding["work_ref"],
        "revision": value["revision"],
        "workflow": "passive-invoice-audit",
        "run_status": loaded["run"]["status"],
        "runtime": value["runtime"],
        "items": rows[offset : offset + 30],
        "source_index": {row["id"]: row["title"] for row in rows},
        "total": len(rows),
        "offset": offset,
        "has_more": offset + 30 < len(rows),
        "draft": draft(value, binding, api),
        "qualified": state["qualification"] if state else None,
        "operator_review": state["operator_review"] if state else None,
        "recipe": state["recipe"] if state else None,
        "operation": (
            {
                key: operation[key]
                for key in ("operation_ref", "status", "error")
                if key in operation
            }
            if operation
            else None
        ),
        "operation_live": value["live"],
        "interrupted": bool(value["unsettled"] and not value["live"]),
        "can_edit": writable,
        "can_launch": writable
        and bool(state)
        and state["operator_review"]["scope"] == scoped(binding),
        "artifacts": sorted(value["population"]),
        "data": {"selection": {"source_ref": state["job_ref"] if state else None}},
    }


def dispatch(
    tool: str, args: dict, binding: dict, loaded: dict, root: Path, api: Any
) -> dict:
    if tool.startswith("vera_workspace_passive_review_"):
        from native_passive_review import dispatch as review_dispatch

        return review_dispatch(tool, args, root, binding, loaded, api)
    if tool == "vera_workspace_passive_setup":
        return setup(root, binding, loaded, args, api)
    value = current(root, binding, loaded, api)
    if tool == "vera_workspace_passive_outputs":
        read_prepared(root, binding, loaded, args, api)
        names = {
            "full_population.jsonl",
            "ledger_entries_without_invoice.jsonl",
            "run_summary.json",
            "run_summary.md",
            "exception_workpaper.xlsx",
        }
        return {
            "work_ref": binding["work_ref"],
            "revision": value["revision"],
            "professional_approval": False,
            "archive_completed": False,
            "outputs": [
                {
                    "name": name,
                    "path": str(Path(loaded["output_dir"]) / name),
                    "sha256": digest,
                }
                for name, digest in sorted(value["population"].items())
                if name in names
            ],
        }
    if tool in {"vera_workspace_passive_view", "vera_workspace_passive_explain"}:
        if tool == "vera_workspace_passive_explain" and args.get("view") == "SOURCE":
            selected = dispatch(
                "vera_workspace_passive_source", args, binding, loaded, root, api
            )["selection"]
        else:
            prepared = read_prepared(root, binding, loaded, args, api)
            selected = prepared["selection"]
        if tool == "vera_workspace_passive_explain":
            if selected is None or len(json.dumps(selected).encode()) > 64_000:
                raise ValueError(
                    "Choose one bounded exact source/evidence page for discussion"
                )
            return {
                "work_ref": binding["work_ref"],
                "revision": value["revision"],
                "untrusted_evidence": selected,
                "purpose": "Explicitly selected source excerpt or JSON member page only; no full-population access or professional approval",
            }
        return {
            **prepared,
            "work_ref": binding["work_ref"],
            "kind": "passive",
            "workflow": "passive-invoice-audit",
            "run_status": loaded["run"]["status"],
            "view": args.get("view", "exceptions"),
            "offset": args.get("offset", 0),
            "has_more": args.get("offset", 0) + 30 < prepared["total"],
        }
    inputs = {row["binding_id"]: row for row in loaded["context"]["input_bindings"]}
    if tool == "vera_workspace_passive_source":
        if (
            args.get("revision") != value["revision"]
            or args.get("item_id") not in inputs
        ):
            raise ValueError("Choose an exact current source")
        row = inputs[args["item_id"]]
        data = ordinary(Path(row["path"]))
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Registered invoice source changed")
        text_source = Path(row["path"]).suffix.lower() in {
            ".csv",
            ".tsv",
            ".txt",
            ".json",
            ".jsonl",
            ".xml",
            ".md",
        }
        if (
            current(root, binding, api.load_binding(binding), api)["revision"]
            != value["revision"]
        ):
            raise ValueError("Invoice source changed during retrieval")
        return {
            "work_ref": binding["work_ref"],
            "revision": value["revision"],
            "file": {"path": row["path"], "sha256": row["sha256"]},
            "selection": {
                "id": row["binding_id"],
                "title": Path(row["path"]).name,
                "sha256": row["sha256"],
                "size_bytes": len(data),
                "excerpt": (
                    data[:20_000].decode("utf-8", errors="replace")
                    if text_source
                    else None
                ),
                "excerpt_truncated": text_source and len(data) > 20_000,
                "preview": "text_excerpt" if text_source else "binary_metadata_only",
            },
            "data": {"selection": {"source_ref": None}},
        }
    if tool == "vera_workspace_passive_status":
        return setup(root, binding, loaded, args, api)
    if tool not in {
        "vera_workspace_passive_draft_save",
        "vera_workspace_passive_draft_clear",
        "vera_workspace_passive_qualify",
        "vera_workspace_passive_launch",
    }:
        raise ValueError("Unknown passive-invoice action")
    if (
        "REVIEWER" not in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
        or loaded["run"]["status"] != "running"
    ):
        raise PermissionError(
            "Invoice writes require reviewer authority and a running run"
        )
    if tool == "vera_workspace_passive_launch":
        key = args.get("idempotency_key")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
            raise ValueError("Invalid invoice launch key")
        identity = api.digest([scoped(binding), key])
        path = value["private"] / ("passive-operation-" + identity + ".json")
        previous = read_record(path, api)
        if previous:
            if previous["request_sha256"] != api.digest([tool, scoped(binding), args]):
                raise ValueError("Invoice launch key belongs to another request")
            return {
                "accepted": True,
                "operation_ref": identity,
                "status": previous["status"],
                "operation_live": lease_alive(
                    value["private"] / ("passive-lease-" + identity + ".lock")
                ),
            }
    if value["unsettled"]:
        raise ValueError(
            "Invoice operation is active or uncertain; inspect the existing job without restarting"
        )
    with api.write_lock(Path(loaded["output_dir"])):
        if api.load_binding(binding) != loaded:
            raise ValueError("Invoice run changed before writing")
        latest = current(root, binding, loaded, api)
        if latest["revision"] != args.get("revision") or (
            latest["state"]["job_ref"] if latest["state"] else None
        ) != args.get("source_ref"):
            raise ValueError(
                "Invoice intake, outputs or operation changed; reopen the work"
            )
        stored = draft(latest, binding, api)
        if args.get("expected_draft_revision") != stored["draft_revision"]:
            raise ValueError("Invoice draft changed in another view")
        if tool.endswith("_draft_clear"):
            draft_path(latest, binding, api).unlink(missing_ok=True)
            return {"cleared": True}
        if tool.endswith("_draft_save"):
            api.ui_state_directory(Path(loaded["output_dir"]))
            saved = save_record(
                draft_path(latest, binding, api),
                {
                    "scope": scoped(binding),
                    "revision": latest["revision"],
                    "fields": fields(args["fields"], inputs),
                },
                api,
            )
            return {"draft_revision": saved["record_sha256"]}
        if args.get("human_reviewed") is not True:
            raise ValueError("Explicit review is required")
        if tool.endswith("_qualify"):
            if stored["stale"]:
                raise ValueError(
                    "Recover current source choices explicitly before qualifying"
                )
            chosen = fields(args["fields"], inputs)
            if any(
                not chosen.get(key, "").strip()
                for key in ("operator_ref", "decision_basis")
            ):
                raise ValueError("Record actual operator and decision basis")
            chosen_recipe = recipe(chosen)
            qualification = engine(
                root,
                {
                    "operation": "plan",
                    "context": str(loaded["context_path"]),
                    "recipe": chosen_recipe,
                },
            )
            if (Path(loaded["output_dir"]) / "audit.sqlite3").exists():
                engine(
                    root,
                    {
                        "operation": "inspect",
                        "context": str(loaded["context_path"]),
                        "recipe": chosen_recipe,
                    },
                )
            if (
                api.load_binding(binding) != loaded
                or job_population(Path(loaded["output_dir"])) != latest["population"]
            ):
                raise ValueError("Invoice sources or job changed during qualification")
            reviewed = {
                "run_scope": [
                    binding[key] for key in ("client_id", "engagement_id", "run_id")
                ],
                "recipe": chosen_recipe,
                "job_ref": qualification["job_ref"],
                "qualification": qualification,
                "operator_review": {
                    "operator_ref": chosen["operator_ref"],
                    "decision_basis": chosen["decision_basis"],
                    "scope": scoped(binding),
                },
            }
            review_ref = api.digest(reviewed)
            review_path = latest["private"] / (
                "passive-qualification-" + review_ref + ".json"
            )
            if review_path.exists():
                if read_record(review_path, api) != {
                    **reviewed,
                    "record_sha256": review_ref,
                }:
                    raise ValueError("Previous immutable invoice qualification changed")
            else:
                save_record(review_path, reviewed, api)
            save_record(
                latest["private"] / "passive-state.json",
                {
                    "run_scope": [
                        binding[key] for key in ("client_id", "engagement_id", "run_id")
                    ],
                    "recipe": chosen_recipe,
                    "job_ref": qualification["job_ref"],
                    "qualification": qualification,
                    "qualification_ref": review_ref,
                    "operator_review": {
                        "operator_ref": chosen["operator_ref"],
                        "decision_basis": chosen["decision_basis"],
                        "scope": scoped(binding),
                    },
                    "operation_ref": (
                        latest["state"].get("operation_ref")
                        if latest["state"]
                        else None
                    ),
                },
                api,
            )
            draft_path(latest, binding, api).unlink(missing_ok=True)
        else:
            state = latest["state"]
            if state is None:
                raise ValueError("Review the exact source recipe first")
            if state["operator_review"]["scope"] != scoped(binding):
                raise PermissionError(
                    "Review source scope with the current operator before launching"
                )
            # Requalify actual receipts before any worker or persistent producer writes.
            qualification = engine(
                root,
                {
                    "operation": "plan",
                    "context": str(loaded["context_path"]),
                    "recipe": state["recipe"],
                },
            )
            if qualification != state["qualification"]:
                raise ValueError("Reviewed invoice qualification changed")
            api.ui_state_directory(Path(loaded["output_dir"]))
            request = {
                "operation_ref": identity,
                "run_scope": state["run_scope"],
                "binding": binding,
                "scope": scoped(binding),
                "recipe": state["recipe"],
                "job_ref": state["job_ref"],
                "population": latest["population"],
                "implementation": latest["implementation"],
                "loaded_run": loaded["run"],
                "input_manifest": loaded["input_manifest"],
                "request_sha256": api.digest([tool, scoped(binding), args]),
                "status": "accepted",
            }
            save_record(path, request, api)
            save_record(
                latest["private"] / "passive-state.json",
                {**state, "operation_ref": identity},
                api,
            )
    if tool.endswith("_qualify"):
        return setup(root, binding, api.load_binding(binding), {}, api)
    log = value["private"] / ("passive-operation-" + identity + ".log")
    with log.open("xb") as diagnostics:
        log.chmod(0o600)
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                str(Path(__file__).with_name("native_passive_supervisor.py")),
                str(root),
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=diagnostics,
            start_new_session=os.name != "nt",
        )
    # Wait only for an acknowledgement, not the audit. A timeout preserves intent
    # and the same operation handle; it never spawns an additional job.
    acknowledgement: queue.Queue = queue.Queue()

    def read_ack() -> None:
        assert process.stdout is not None
        acknowledgement.put(process.stdout.readline(4096))

    threading.Thread(target=read_ack, daemon=True).start()
    try:
        acknowledgement.get(timeout=10)
    except queue.Empty:
        pass
    receipt = read_record(path, api)
    return {
        "accepted": True,
        "operation_ref": identity,
        "status": receipt["status"],
        "operation_live": lease_alive(
            value["private"] / ("passive-lease-" + identity + ".lock")
        ),
    }


def read_prepared(
    root: Path, binding: dict, loaded: dict, args: dict, api: Any
) -> dict:
    value = current(root, binding, loaded, api)
    state = value["state"]
    if args.get("revision") and args["revision"] != value["revision"]:
        raise ValueError("Invoice source or job revision changed")
    if state is None or args.get("source_ref") != state["job_ref"]:
        raise ValueError("Choose the exact reviewed invoice job")
    if value["unsettled"]:
        raise ValueError(
            "Invoice job is active or uncertain; use its live status panel"
        )
    inspected = engine(
        root,
        {
            "operation": "inspect",
            "context": str(loaded["context_path"]),
            "recipe": state["recipe"],
            "args": {
                key: args[key] for key in ("view", "offset", "item_id") if key in args
            }
            | ({"source_ref": args["member_ref"]} if args.get("member_ref") else {}),
        },
    )
    selected = inspected["selection"]
    if (
        current(root, binding, api.load_binding(binding), api)["revision"]
        != value["revision"]
    ):
        raise ValueError("Invoice job changed during native view retrieval")
    if selected is not None:
        selected = {
            "id": args["item_id"],
            "title": args["item_id"],
            "evidence_page": selected,
        }
    return {
        "revision": value["revision"],
        "items": inspected["items"],
        "total": inspected["total"],
        "selection": selected,
        "data": {
            "selection": {"source_ref": state["job_ref"]},
            "status": inspected["status"],
            "summary": inspected.get("summary"),
            "artifacts": inspected.get("artifacts", []),
            "professional_approval": False,
        },
    }
