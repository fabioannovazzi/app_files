"""Recoverable human labels and immutable public evaluation, separate from screening."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from native_bank_preparation import file_hash
from native_passive_audit import MAX_ROWS, job_population, ordinary
from native_passive_service import (
    current,
    read_prepared,
    read_record,
    save_record,
    scoped,
)
from native_passive_supervisor import producer_guard

__all__ = ["dispatch"]
LABELS = {"problematic", "acceptable", "ambiguous"}


def evaluate(root: Path, loaded: dict, reference: str, operation: str) -> dict:
    """Use only the fixed isolated evaluator and server-derived owned reference."""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("native_passive_review_bridge.py")),
            str(root),
        ],
        input=json.dumps(
            {
                "context": str(loaded["context_path"]),
                "review_ref": reference,
                "operation": operation,
            }
        ),
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ValueError(
            result.stderr.strip().splitlines()[-1] or "Public label evaluation refused"
        )
    return json.loads(result.stdout)


def snapshot(root: Path, binding: dict, loaded: dict, api: Any) -> dict:
    value = current(root, binding, loaded, api)
    if value["state"] is None or value["unsettled"]:
        raise ValueError("Review the exact settled public invoice job first")
    prepared = read_prepared(
        root,
        binding,
        loaded,
        {
            "source_ref": value["state"]["job_ref"],
            "revision": value["revision"],
            "view": "population",
        },
        api,
    )
    output = Path(loaded["output_dir"])
    data = ordinary(output / "full_population.jsonl")
    if hashlib.sha256(data).hexdigest() != value["population"].get(
        "full_population.jsonl"
    ):
        raise ValueError("Screening population changed during label preparation")
    rows = [json.loads(line) for line in data.splitlines() if line.strip()]
    if len(rows) > MAX_ROWS:
        raise ValueError("Human review exceeds qualified native population limit")
    head = read_record(value["private"] / "passive-review-head.json", api)
    if head and head["run_scope"] != [
        binding[key] for key in ("client_id", "engagement_id", "run_id")
    ]:
        raise PermissionError("Review head belongs to another run")
    review_implementation = [
        file_hash(Path(__file__)),
        file_hash(Path(__file__).with_name("native_passive_review_bridge.py")),
    ]
    revision = api.digest(
        [
            value["revision"],
            head,
            *review_implementation,
        ]
    )
    return {
        **value,
        "base_revision": value["revision"],
        "review_implementation": review_implementation,
        "revision": revision,
        "rows": rows,
        "population_bytes": data,
        "population_sha256": hashlib.sha256(data).hexdigest(),
        "head": head,
        "screening_status": prepared["data"]["status"],
    }


def draft_directory(value: dict, binding: dict, api: Any) -> Path:
    return value["private"] / ("passive-label-draft-" + api.digest(scoped(binding)))


def unchanged(root: Path, binding: dict, value: dict, api: Any) -> None:
    """Check source scope and physical population again after selected reads."""
    if (
        current(root, binding, api.load_binding(binding), api)["revision"]
        != value["base_revision"]
        or read_record(value["private"] / "passive-review-head.json", api)
        != value["head"]
        or [
            file_hash(Path(__file__)),
            file_hash(Path(__file__).with_name("native_passive_review_bridge.py")),
        ]
        != value["review_implementation"]
    ):
        raise ValueError("Human review changed during retrieval")


def read_draft(value: dict, binding: dict, api: Any) -> dict:
    folder = draft_directory(value, binding, api)
    if folder.is_symlink():
        raise ValueError("Human label draft cannot use a linked directory")
    head = read_record(folder / "head.json", api)
    if head and head["scope"] != scoped(binding):
        raise PermissionError("Label draft belongs to another actor or run")
    return {
        "head": head,
        "draft_revision": head["record_sha256"] if head else "",
        "exists": bool(head),
        "stale": bool(head and head["revision"] != value["revision"]),
        "damaged": bool(
            head
            and any(
                not (folder / (reference + ".json")).exists()
                for reference in head["buckets"].values()
            )
        ),
    }


def draft_fields(value: dict, binding: dict, draft: dict, api: Any) -> dict:
    """Content-addressed shards support the complete population without one giant form."""
    merged = {}
    if not draft["head"]:
        return merged
    for bucket, ref in draft["head"]["buckets"].items():
        if not re.fullmatch(r"[0-9a-f]{2}", bucket) or not re.fullmatch(
            r"[0-9a-f]{64}", ref
        ):
            raise ValueError("Invalid human draft shard")
        record = read_record(
            draft_directory(value, binding, api) / (ref + ".json"), api
        )
        if (
            record is None
            or record["scope"] != scoped(binding)
            or record["population_sha256"] != draft["head"]["population_sha256"]
            or record["bucket"] != bucket
        ):
            raise ValueError("Label draft shard is missing or foreign")
        merged.update(record["entries"])
    return merged


def review(root: Path, loaded: dict, value: dict, reference: str, api: Any) -> dict:
    if not isinstance(reference, str) or not re.fullmatch(r"[0-9a-f]{64}", reference):
        raise ValueError("Choose an exact human review version")
    folder = Path(loaded["output_dir"]) / "professional_reviews" / reference
    record = api.read_json(folder / "review.json")
    if api.digest(record) != reference or record["run_scope"] != [
        loaded["context"][key] for key in ("client_id", "engagement_id", "run_id")
    ]:
        raise ValueError("Human review record changed or is foreign")
    receipts = [
        read_record(path, api)
        for path in value["private"].glob("passive-label-operation-*.json")
    ]
    sealed = [
        row
        for row in receipts
        if row and row.get("review_ref") == reference and row["status"] == "completed"
    ]
    if len(sealed) != 1 or any(
        value["population"].get(name) != digest
        for name, digest in sealed[0]["artifacts"].items()
    ):
        raise ValueError("Human review files differ from their completed receipt")
    evaluate(root, loaded, reference, "verify")
    labels = [
        json.loads(line)
        for line in ordinary(folder / "labels.jsonl").splitlines()
        if line.strip()
    ]
    result = json.loads(ordinary(folder / "evaluation.json"))
    return {
        "reference": reference,
        "record": record,
        "labels": {row["invoice_id"]: row for row in labels},
        "evaluation": result,
        "current_population": record["population_sha256"] == value["population_sha256"]
        and record["job_ref"] == value["state"]["job_ref"],
    }


def pending(value: dict, binding: dict, api: Any) -> list:
    rows = []
    for path in value["private"].glob("passive-label-operation-*.json"):
        receipt = read_record(path, api)
        if receipt is None or receipt["run_scope"] != [
            binding[key] for key in ("client_id", "engagement_id", "run_id")
        ]:
            raise ValueError("Label operation receipt is foreign")
        if receipt["status"] != "completed":
            rows.append(
                {"operation_ref": receipt["operation_ref"], "status": receipt["status"]}
            )
    return rows


def clear_draft(directory: Path, binding: dict, api: Any) -> None:
    """Discard only verified records in this actor/run's private draft namespace."""
    if not directory.exists():
        return
    paths = list(directory.iterdir())
    if len(paths) > 100_000:
        raise ValueError("Private draft cleanup exceeds inspection limit")
    for path in paths:
        if path.name != "head.json" and not re.fullmatch(
            r"[0-9a-f]{64}\.json", path.name
        ):
            raise ValueError("Unknown private draft file; preserve it for inspection")
        record = read_record(path, api)
        if record is None or record["scope"] != scoped(binding):
            raise PermissionError("Cannot discard a foreign human draft")
    for path in paths:
        path.unlink()
    directory.rmdir()


@contextmanager
def write_guard(
    value: dict, binding: dict, args: dict, outcome: dict, api: Any
) -> Iterator[None]:
    """A terminal review receipt requires a clean ownership-guard exit."""
    exited = False
    try:
        with producer_guard(
            value["private"] / "write.lock", api.digest([scoped(binding), args])
        ):
            yield
        exited = True
    finally:
        if outcome.get("intent"):
            save_record(
                outcome["path"],
                {
                    **outcome["intent"],
                    "status": (
                        "completed"
                        if exited and outcome.get("artifacts")
                        else "uncertain"
                    ),
                    "artifacts": outcome.get("artifacts", {}),
                },
                api,
            )


def dispatch(
    tool: str, args: dict, root: Path, binding: dict, loaded: dict, api: Any
) -> dict:
    value = snapshot(root, binding, loaded, api)
    draft = read_draft(value, binding, api)
    unresolved = pending(value, binding, api)
    reference = args.get("review_ref") or (
        value["head"]["review_ref"] if value["head"] else None
    )
    confirmed = (
        review(root, loaded, value, reference, api)
        if reference and (not unresolved or args.get("review_ref"))
        else None
    )
    if tool == "vera_workspace_passive_review_setup":
        offset = args.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("Invalid human review page")
        fields = (
            draft_fields(value, binding, draft, api)
            if not draft["stale"] and not draft["damaged"]
            else {}
        )
        historical = bool(args.get("review_ref"))
        display_rows = value["rows"]
        if historical and confirmed and not confirmed["current_population"]:
            path = (
                Path(loaded["output_dir"])
                / "professional_review_populations"
                / (confirmed["record"]["population_sha256"] + ".jsonl")
            )
            display_rows = [
                json.loads(line) for line in ordinary(path).splitlines() if line.strip()
            ]
        labels = (
            confirmed["labels"]
            if confirmed and (confirmed["current_population"] or historical)
            else {}
        )
        proposed = dict(labels) if not historical else {}
        for identity, entry in fields.items():
            if entry["label"]:
                proposed[identity] = entry
            else:
                proposed.pop(identity, None)
        versions = sorted(
            {
                name.split("/")[1]
                for name in value["population"]
                if re.fullmatch(r"professional_reviews/[0-9a-f]{64}/review.json", name)
            }
        )
        unchanged(root, binding, value, api)
        return {
            "work_ref": binding["work_ref"],
            "revision": value["revision"],
            "data": {"selection": {"source_ref": value["state"]["job_ref"]}},
            "screening_status": value["screening_status"],
            "draft": {
                key: draft[key]
                for key in ("exists", "stale", "damaged", "draft_revision")
            }
            | {"proposed_labelled_count": len(proposed)},
            "operator_ref": (
                draft["head"]["operator_ref"]
                if draft["head"] and not draft["stale"]
                else ""
            ),
            "decision_basis": (
                draft["head"]["decision_basis"]
                if draft["head"] and not draft["stale"]
                else ""
            ),
            "items": [
                {
                    "id": row["invoice"]["invoice_id"],
                    "title": row["invoice"].get(
                        "invoice_number", row["invoice"]["invoice_id"]
                    ),
                    "screening_state": row["final_state"],
                    "semantic_status": (row.get("semantic_result") or {}).get(
                        "status", "not_run"
                    ),
                    "reviewed": labels.get(row["invoice"]["invoice_id"]),
                    "draft": fields.get(row["invoice"]["invoice_id"]),
                }
                for row in display_rows[offset : offset + 30]
            ],
            "offset": offset,
            "total": len(display_rows),
            "has_more": offset + 30 < len(display_rows),
            "versions": versions,
            "selected_review": (
                {
                    "review_ref": reference,
                    "record": confirmed["record"],
                    "current_population": confirmed["current_population"],
                    "metrics": {
                        key: row
                        for key, row in confirmed["evaluation"].items()
                        if key != "missed_material_issues"
                    },
                    "missed_material_issues": confirmed["evaluation"][
                        "missed_material_issues"
                    ][offset : offset + 30],
                    "missed_total": len(
                        confirmed["evaluation"]["missed_material_issues"]
                    ),
                }
                if confirmed
                else None
            ),
            "pending": unresolved,
            "can_edit": loaded["run"]["status"] == "running"
            and "REVIEWER" in os.environ.get("VERA_WORKSPACE_ROLES", "").split(",")
            and not unresolved
            and not historical,
            "professional_approval": False,
        }
    if tool == "vera_workspace_passive_review_explain":
        if (
            confirmed is None
            or args.get("revision") != value["revision"]
            or args.get("source_ref") != value["state"]["job_ref"]
        ):
            raise ValueError("Choose exact current scope and human-review version")
        identity = args.get("item_id", "")
        if identity.startswith("missed:"):
            selected = next(
                (
                    row
                    for row in confirmed["evaluation"]["missed_material_issues"]
                    if row["invoice_id"] == identity[7:]
                ),
                None,
            )
        else:
            selected = confirmed["labels"].get(identity)
        if selected is None:
            raise ValueError("Choose one exact authored label or missed issue")
        unchanged(root, binding, value, api)
        return {
            "untrusted_evidence": {
                "review_ref": reference,
                "current_population": confirmed["current_population"],
                "item_id": identity,
                "value": selected,
            },
            "professional_approval": False,
        }
    if tool == "vera_workspace_passive_review_outputs":
        if (
            confirmed is None
            or args.get("revision") != value["revision"]
            or args.get("source_ref") != value["state"]["job_ref"]
        ):
            raise ValueError("Choose a current exact human review and scope")
        names = [
            "professional_reviews/" + reference + "/" + name
            for name in ("review.json", "labels.jsonl", "evaluation.json")
        ]
        names.append(
            "professional_review_populations/"
            + confirmed["record"]["population_sha256"]
            + ".jsonl"
        )
        unchanged(root, binding, value, api)
        return {
            "outputs": [
                {
                    "name": name,
                    "path": str(Path(loaded["output_dir"]) / name),
                    "sha256": value["population"][name],
                }
                for name in names
            ],
            "professional_approval": False,
        }
    if loaded["run"]["status"] != "running" or "REVIEWER" not in os.environ.get(
        "VERA_WORKSPACE_ROLES", ""
    ).split(","):
        raise PermissionError(
            "Human labels require reviewer authority and a running run"
        )
    operation_path = None
    if tool == "vera_workspace_passive_review_publish":
        key = args.get("idempotency_key", "")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", key):
            raise ValueError("Invalid human review publication key")
        identity = api.digest([scoped(binding), key])
        operation_path = value["private"] / (
            "passive-label-operation-" + identity + ".json"
        )
        previous = read_record(operation_path, api)
        if previous:
            if previous["request_sha256"] != api.digest(args):
                raise ValueError("Review key belongs to another request")
            if previous["status"] == "completed":
                review(root, loaded, value, previous["review_ref"], api)
            return {
                "status": previous["status"],
                "review_ref": previous.get("review_ref"),
                "operation_ref": identity,
                "professional_approval": False,
            }
    if unresolved:
        raise ValueError(
            "Human review write is uncertain; inspect retained evidence without repeating"
        )
    api.ui_state_directory(Path(loaded["output_dir"]))
    outcome: dict = {}
    with write_guard(value, binding, args, outcome, api):
        if (
            api.load_binding(binding) != loaded
            or snapshot(root, binding, loaded, api)["revision"] != value["revision"]
            or args.get("revision") != value["revision"]
            or args.get("source_ref") != value["state"]["job_ref"]
        ):
            raise ValueError("Human review population or scope changed")
        if args.get("expected_draft_revision") != draft["draft_revision"]:
            raise ValueError("Human label draft changed in another view")
        directory = draft_directory(value, binding, api)
        if tool == "vera_workspace_passive_review_draft_clear":
            clear_draft(directory, binding, api)
            return {"cleared": True}
        if tool == "vera_workspace_passive_review_draft_save":
            if draft["stale"] or draft["damaged"]:
                raise ValueError(
                    "Recover or explicitly discard stale or incomplete human draft"
                )
            changes = args.get("entries", {})
            ids = {row["invoice"]["invoice_id"] for row in value["rows"]}
            if (
                not isinstance(changes, dict)
                or len(changes) > 30
                or any(
                    key not in ids
                    or not isinstance(entry, dict)
                    or set(entry) != {"label", "known_issue"}
                    or entry["label"] not in LABELS | {""}
                    or not isinstance(entry["known_issue"], str)
                    or len(entry["known_issue"]) > 2000
                    for key, entry in changes.items()
                )
            ):
                raise ValueError("Choose at most thirty exact unfinished human labels")
            for name in ("operator_ref", "decision_basis"):
                if not isinstance(args.get(name), str) or len(args[name]) > 4000:
                    raise ValueError("Invalid unfinished human review attribution")
            directory.mkdir(mode=0o700, exist_ok=True)
            buckets = dict(draft["head"]["buckets"]) if draft["head"] else {}
            for bucket in {
                hashlib.sha256(key.encode()).hexdigest()[:2] for key in changes
            }:
                prior = (
                    read_record(directory / (buckets[bucket] + ".json"), api)
                    if bucket in buckets
                    else None
                )
                entries = dict(prior["entries"]) if prior else {}
                entries.update(
                    {
                        key: entry
                        for key, entry in changes.items()
                        if hashlib.sha256(key.encode()).hexdigest()[:2] == bucket
                    }
                )
                record = {
                    "scope": scoped(binding),
                    "population_sha256": value["population_sha256"],
                    "bucket": bucket,
                    "entries": entries,
                }
                ref = api.digest(record)
                path = directory / (ref + ".json")
                if path.exists() and read_record(path, api) != {
                    **record,
                    "record_sha256": ref,
                }:
                    raise ValueError("Immutable unfinished label shard changed")
                save_record(path, record, api)
                buckets[bucket] = ref
            head = save_record(
                directory / "head.json",
                {
                    "scope": scoped(binding),
                    "population_sha256": value["population_sha256"],
                    "revision": value["revision"],
                    "buckets": buckets,
                    "operator_ref": args["operator_ref"],
                    "decision_basis": args["decision_basis"],
                },
                api,
            )
            return {"draft_revision": head["record_sha256"]}
        if tool != "vera_workspace_passive_review_publish":
            raise ValueError("Unknown human review operation")
        if (
            args.get("human_reviewed") is not True
            or draft["stale"]
            or draft["damaged"]
            or draft["head"] is None
            or not draft["head"]["operator_ref"].strip()
            or not draft["head"]["decision_basis"].strip()
        ):
            raise ValueError(
                "Explicit complete human attribution and current draft are required"
            )
        labels = (
            dict(confirmed["labels"])
            if confirmed and confirmed["current_population"]
            else {}
        )
        for invoice_id, entry in draft_fields(value, binding, draft, api).items():
            if entry["label"]:
                labels[invoice_id] = {"invoice_id": invoice_id, **entry}
            else:
                labels.pop(invoice_id, None)
        if not labels:
            raise ValueError("Evaluation requires explicitly reviewed labels")
        label_bytes = b"".join(
            (
                json.dumps(labels[key], ensure_ascii=False, sort_keys=True) + "\n"
            ).encode()
            for key in sorted(labels)
        )
        record = {
            "schema_version": "vera.native_passive_human_review.v1",
            "run_scope": [
                binding[key] for key in ("client_id", "engagement_id", "run_id")
            ],
            "scope": scoped(binding),
            "source_revision": value["revision"],
            "job_ref": value["state"]["job_ref"],
            "population_sha256": value["population_sha256"],
            "labels_sha256": hashlib.sha256(label_bytes).hexdigest(),
            "parent_review_ref": value["head"]["review_ref"] if value["head"] else None,
            "operator_ref": draft["head"]["operator_ref"],
            "decision_basis": draft["head"]["decision_basis"],
            "screening_status": value["screening_status"],
            "professional_approval": False,
        }
        reference = api.digest(record)
        intent = {
            "run_scope": record["run_scope"],
            "scope": scoped(binding),
            "operation_ref": identity,
            "review_ref": reference,
            "request_sha256": api.digest(args),
            "status": "accepted",
        }
        save_record(operation_path, intent, api)
        outcome.update({"intent": intent, "path": operation_path})
        output = Path(loaded["output_dir"])
        folder = output / "professional_reviews" / reference
        retained = (
            output
            / "professional_review_populations"
            / (value["population_sha256"] + ".jsonl")
        )
        succeeded = False
        try:
            folder.mkdir(parents=True, mode=0o700, exist_ok=False)
            retained.parent.mkdir(mode=0o700, exist_ok=True)
            if retained.exists():
                if ordinary(retained) != value["population_bytes"]:
                    raise ValueError("Retained human population changed")
            else:
                with retained.open("xb") as stream:
                    stream.write(value["population_bytes"])
            with (folder / "labels.jsonl").open("xb") as stream:
                stream.write(label_bytes)
            api.atomic_json(folder / "review.json", record)
            evaluate(root, loaded, reference, "evaluate")
            observed = job_population(output)
            expected = {
                **value["population"],
                **{
                    name: digest
                    for name, digest in observed.items()
                    if name
                    in {
                        "professional_reviews/" + reference + "/" + basename
                        for basename in (
                            "review.json",
                            "labels.jsonl",
                            "evaluation.json",
                        )
                    }
                    or name == retained.relative_to(output).as_posix()
                },
            }
            if (
                observed != expected
                or api.load_binding(binding) != loaded
                or current(root, binding, loaded, api)["implementation"]
                != value["implementation"]
                or [
                    file_hash(Path(__file__)),
                    file_hash(
                        Path(__file__).with_name("native_passive_review_bridge.py")
                    ),
                ]
                != value["review_implementation"]
            ):
                raise ValueError(
                    "Unrelated source or output changed during human evaluation"
                )
            save_record(
                value["private"] / "passive-review-head.json",
                {"run_scope": record["run_scope"], "review_ref": reference},
                api,
            )
            clear_draft(directory, binding, api)
            succeeded = True
        finally:
            outcome["artifacts"] = (
                {
                    name: digest
                    for name, digest in job_population(output).items()
                    if name.startswith("professional_reviews/" + reference + "/")
                    or name == retained.relative_to(output).as_posix()
                }
                if succeeded
                else {}
            )
        return {
            "status": "completed",
            "review_ref": reference,
            "professional_approval": False,
            "archive_completed": False,
        }
