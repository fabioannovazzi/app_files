"""Bounded evidence-request orchestration inside the existing isolated worker contract."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

import bank_first as bf
from evidence_retrieval import (
    DEFAULT_BUDGET,
    EvidenceIndex,
    RetrievalLimit,
    query_schema,
)

__all__ = ["run_review", "replay_result", "extend_schema"]
PROTOCOL = "vera.retrieval.v1"


def extend_schema(schema: dict) -> dict:
    schema = copy.deepcopy(schema)
    p = schema["properties"]
    p["groups"]["minItems"] = 0
    p["evidence_requests"] = {"type": "array", "maxItems": 4, "items": query_schema()}
    p["retain"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            s: {"type": "array", "maxItems": 64, "items": {"type": "string"}}
            for s in ("bank", "journal")
        },
        "required": ["bank", "journal"],
    }
    p["working_note"] = {"type": "string", "maxLength": 2400}
    schema["required"] += ["evidence_requests", "retain", "working_note"]
    return schema


def _search_notes(pages):
    """Keep query/coverage metadata, never duplicate retrieved source rows."""
    return [
        {
            k: page[k]
            for k in (
                "query",
                "total_candidates",
                "returned",
                "remaining_unread",
                "next_cursor",
            )
        }
        for page in pages
    ]


def _initial(index, focus, groups):
    bank_ids = {i for f in focus for i in f["bank_ids"]}
    prior = [g for g in groups if bank_ids.intersection(g["bank_ids"])]
    anchors = {
        "bank": sorted(bank_ids),
        "journal": sorted({i for g in prior for i in g["journal_ids"]}),
    }
    queries = []
    # Exact identifiers and amounts are starting leads, never semantic decisions.
    for row in index.get("bank", anchors["bank"])[:4]:
        if row.get("reference"):
            queries.append(
                {"side": "journal", "field": "reference", "value": row["reference"]}
            )
        else:
            queries.append(
                {
                    "side": "journal",
                    "amount_min": row["amount_signed"],
                    "amount_max": row["amount_signed"],
                }
            )
    unique = {bf.digest(q): q for q in queries}
    pages = [index.search(q) for q in unique.values()]
    return {
        "anchors": anchors,
        "pages": pages,
        "retain": {"bank": [], "journal": []},
        "working_note": "",
        "recent_searches": _search_notes(pages),
        "search_count": len(pages),
        "round": 0,
        "parent": None,
    }


def _packet(
    index,
    session,
    focus,
    groups,
    admitted,
    binding,
    relationship,
    stage,
    purpose,
    budget,
):
    selected = {
        s: set(session["anchors"][s]) | set(session["retain"][s])
        for s in ("bank", "journal")
    }
    for page in session["pages"]:
        for ref in page["records"]:
            selected[ref["side"]].add(ref["transaction_id"])
    focus_ids = {i for f in focus for i in f["bank_ids"]}
    # Keep the latest complete prior group for carry-forward, not recursive history.
    relevant = [g for g in groups if selected["bank"].intersection(g["bank_ids"])]
    for g in relevant:
        selected["bank"].update(g["bank_ids"])
        selected["journal"].update(g["journal_ids"])
    rows = {
        s: [bf._project(r) for r in index.get(s, sorted(selected[s]))] for s in selected
    }
    prior = [
        {k: v for k, v in g.items() if k not in {"history", "retrieval_context"}}
        for g in relevant
    ]
    processed = {i for g in groups for i in g["bank_ids"]}
    eligible = {i for i in selected["bank"] if i not in processed} | focus_ids
    if stage == "sol":
        eligible |= {
            i
            for g in relevant
            if g.get("stage") == "luna" and g["bank_resolution"]["status"] != "resolved"
            for i in g["bank_ids"]
        }
    owners = {
        i: g["bank_ids"][0]
        for g in groups
        if g["allocation_state"] == "reserved"
        for i in g["journal_ids"]
    }
    # External owners are reported as unavailable; exact global enforcement follows validation.
    reserved = {
        i: owner
        for i, owner in owners.items()
        if i in selected["journal"] and owner in selected["bank"]
    }
    rel = {k: v for k, v in relationship.items() if k != "documented_aliases"}
    if "strong_pair_ids" in rel:
        rel["strong_pair_ids"] = [
            pair
            for pair in rel["strong_pair_ids"]
            if pair[0] in selected["bank"] and pair[1] in selected["journal"]
        ]
    content = {
        "schema_version": bf.PROTOCOL,
        "workflow_id": binding.get("workflow", "journal-bank-reconciliation"),
        "stage": stage,
        "purpose": purpose,
        "source_binding": dict(binding),
        "policy": bf.policy(),
        "policy_sha256": bf.digest(bf.policy()),
        "relationship_policy": rel,
        "admission_sha256": admitted["content_sha256"],
        "focus": focus,
        "eligible_bank_ids": sorted(eligible),
        "bank_records": rows["bank"],
        "journal_records": rows["journal"],
        "prior_conclusions": prior,
        "reserved_journal_owners": reserved,
        "probable_candidates": [],
        "invoice_closure_authorized": bool(
            relationship.get("open_item_allocation_authorized")
        ),
        "partita_identity_authorized": False,
        "retrieval": {
            "protocol": PROTOCOL,
            "source_index_sha256": index.binding,
            "prior_state_sha256": bf.digest(groups),
            "relationship_sha256": bf.digest(relationship),
            "population_counts": index.counts,
            "visible_counts": {s: len(v) for s, v in selected.items()},
            "not_in_context": {
                s: index.counts[s] - len(v) for s, v in selected.items()
            },
            "pages": session["pages"],
            "working_note": session["working_note"],
            "recent_searches": session["recent_searches"],
            "search_count": session["search_count"],
            "omitted_search_count": session["search_count"]
            - len(session["recent_searches"]),
            "prior_investigations": [
                {
                    "bank_ids": g["bank_ids"],
                    "stage": g["stage"],
                    **g["retrieval_context"],
                }
                for g in relevant
                if "retrieval_context" in g
            ],
            "round": session["round"],
            "parent_packet_sha256": session["parent"],
            "budget": budget,
            "reserved_outside_focus": sorted(
                i
                for i in selected["journal"]
                if i in owners and owners[i] not in focus_ids
            ),
            "record_provenance": [
                {
                    "side": s,
                    "record_id": i,
                    "source": {
                        k: v
                        for k, v in index.rows[s][i].items()
                        if k.startswith("source_")
                        or k in ("row_locator", "group_id", "settlement_id")
                    },
                }
                for s in selected
                for i in sorted(selected[s])
            ],
            "instructions": "Use evidence_requests to search by identifiers, names, documented aliases, exact amounts/ranges, dates or full-text. All filters are optional. field=group_id/settlement_id/reference retrieves linked members; use next_cursor for further pages. field=transaction_id retrieves a known source ID from page records. retain uses current B/J references; retain only useful records. Requests replace previous page context, with anchors and retained records preserved. working_note is your compact fallible investigation summary, not source evidence. Send groups=[] when asking for evidence; send evidence_requests=[] for a decision. Never infer absence from an unread page or technical budget. The local log retains every search. Complete groups must be kept intact; ask for their other members. No arbitrary tools.",
        },
    }
    return {**content, "packet_sha256": bf.digest(content)}


def _advance(index, session, packet, response):
    if response.get("packet_sha256") != packet["packet_sha256"]:
        raise ValueError("Evidence request belongs to another packet")
    requests = response.get("evidence_requests", [])
    if not requests or len(requests) > 4 or response.get("groups"):
        raise ValueError("Evidence turn needs 1–4 queries and no decisions")
    refs = bf.reference_map(packet)
    retain = response.get("retain", {})
    if set(retain) != {"bank", "journal"} or any(
        not isinstance(v, list) or len(v) > 64 for v in retain.values()
    ):
        raise ValueError("Invalid retained working set")
    try:
        kept = {s: [refs[s][ref] for ref in retain[s]] for s in refs}
    except (KeyError, TypeError) as error:
        raise ValueError("Retain references must have been supplied") from error
    note = response.get("working_note", "")
    if not isinstance(note, str) or len(note) > 2400:
        raise ValueError("Working note exceeds bounded memory")
    pages = [index.search(q) for q in requests]
    if (
        pages == session["pages"]
        and kept == session["retain"]
        and note == session["working_note"]
    ):
        raise RetrievalLimit("Repeated evidence request made no progress")
    return {
        **session,
        "pages": pages,
        "retain": kept,
        "working_note": note,
        "recent_searches": (session["recent_searches"] + _search_notes(pages))[-8:],
        "search_count": session["search_count"] + len(pages),
        "round": session["round"] + 1,
        "parent": packet["packet_sha256"],
    }


def _decide(packet, response, groups, domain_validator):
    canonical = bf.decode_response(
        packet,
        {"packet_sha256": response["packet_sha256"], "groups": response["groups"]},
    )
    additions = bf.validate_response(
        packet, canonical, domain_validator=domain_validator
    )
    owners = {
        i: set(g["bank_ids"])
        for g in groups
        if g["allocation_state"] == "reserved"
        for i in g["journal_ids"]
    }
    for group in additions:
        if group["allocation_state"] == "reserved":
            for i in group["journal_ids"]:
                if i in owners and owners[i] != set(group["bank_ids"]):
                    raise ValueError(
                        "Global evidence ownership conflict across subsets/stages"
                    )
    for group in additions:
        group["retrieval_context"] = {
            k: packet["retrieval"][k]
            for k in (
                "recent_searches",
                "search_count",
                "omitted_search_count",
                "working_note",
            )
        }
    return bf._replace_groups(groups, additions)


def _source_check(check):
    if check is not None:
        try:
            check()
        except ValueError as error:
            raise RuntimeError(str(error)) from error


def _settings(value):
    budget = {**DEFAULT_BUDGET, **(value or {})}
    if set(budget) != set(DEFAULT_BUDGET) or any(
        type(v) is not int or v <= 0 for v in budget.values()
    ):
        raise ValueError("Invalid retrieval budget")
    if (
        budget["context_bytes"] > 262144
        or budget["page_rows"] > 64
        or budget["max_rounds"] > 128
    ):
        raise ValueError("Retrieval budget exceeds native technical limits")
    return budget


def _reconstruct(
    index,
    attempts,
    output,
    admitted,
    binding,
    relationship,
    purpose,
    budget,
    domain_validator,
):
    groups = [bf._deterministic(g) for g in admitted["sure"]]
    if domain_validator is not None:
        for group in groups:
            domain_validator(
                group,
                {
                    "bank_records": index.get("bank", group["bank_ids"]),
                    "journal_records": index.get("journal", group["journal_ids"]),
                },
            )
    completed = {"luna": set(), "sol": set()}
    session = None
    active_focus = None
    for attempt in attempts:
        directory = output / "bank-first-attempts" / attempt["directory"]
        if (
            Path(attempt["directory"]).name != attempt["directory"]
            or directory.is_symlink()
        ):
            raise ValueError("Attempt escapes run")
        for name, expected_hash in attempt.get("artifact_sha256", {}).items():
            artifact = directory / name
            if (
                Path(name).name != name
                or artifact.is_symlink()
                or directory.is_symlink()
                or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_hash
            ):
                raise ValueError("Retained native attempt evidence changed")
        if attempt["status"] not in {"validated", "evidence_requested"}:
            continue
        directory = output / "bank-first-attempts" / attempt["directory"]
        if (
            Path(attempt["directory"]).name != attempt["directory"]
            or directory.is_symlink()
        ):
            raise ValueError("Attempt escapes run")
        packet = bf._read(directory / "packet.json")
        stage, focus = packet["stage"], packet["focus"]
        expected_stage = (
            "luna"
            if bf._next_focus(
                list(index.rows["bank"].values()), groups, "luna", completed["luna"]
            )
            else "sol"
        )
        if stage != expected_stage:
            raise ValueError("Retained stage skipped first-stage work")
        if session is None:
            expected_focus = bf._next_focus(
                list(index.rows["bank"].values()), groups, stage, completed[stage]
            )
            if expected_focus != focus:
                raise ValueError("Retained focus changed")
            session = _initial(index, focus, groups)
            active_focus = focus
        if focus != active_focus:
            raise ValueError("Retrieval chain changed focus")
        expected = _packet(
            index,
            session,
            focus,
            groups,
            admitted,
            binding,
            relationship,
            stage,
            purpose,
            budget,
        )
        if packet != expected:
            raise ValueError(
                "Retained evidence differs from indexed sources, search or prior state"
            )
        response = bf._read(directory / "response.json")
        bf.validate_receipt(
            bf._read(directory / "receipt.json"),
            packet,
            response,
            (directory / "prompt.md").read_text(),
            bf._read(directory / "schema.json"),
            attempt["selection"],
        )
        if attempt["status"] == "evidence_requested":
            session = _advance(index, session, packet, response)
        else:
            groups = _decide(packet, response, groups, domain_validator)
            completed[stage].update(
                i
                for g in response["groups"]
                for i in bf.decode_response(packet, {"groups": [g]})["groups"][0][
                    "bank_ids"
                ]
            )
            session = None
    return groups, completed, session


@contextmanager
def _run_lock(output):
    """Prevent simultaneous controllers from allocating against stale run state."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".retrieval.lock"
    if output.is_symlink() or lock.is_symlink():
        raise ValueError("Run storage cannot use symbolic links")
    with lock.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("Another controller owns this run") from error
        else:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Another controller owns this run") from error
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def run_review(bank, journal, output, **kwargs):
    with _run_lock(output):
        return _run_review(bank, journal, output, **kwargs)


def _implementation_digest():
    return bf.digest(
        {
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in (
                "bank_first.py",
                "retrieval_review.py",
                "evidence_retrieval.py",
                "bank_first_policy.json",
            )
        }
    )


def _run_review(
    bank,
    journal,
    output: Path,
    *,
    source_binding,
    relationship,
    invoke=None,
    select=None,
    source_check=None,
    purpose="bank_open_items",
    domain_validator=None,
    worker_selection=None,
    codex_bin=None,
    source_records=None,
    retrieval_budget=None,
):
    """Persist every evidence exchange; resume completed work without model replay."""
    import semantic_review as semantic
    from native_host_worker import NativeWorkerPending

    invoke = invoke or semantic.run_isolated_native_worker
    select = select or semantic.discover_worker_selection
    source_projections = {
        record["record_id"]: record for record in (source_records or [])
    }
    if purpose not in bf.policy()["purposes"]:
        raise ValueError("Unsupported shared reconciliation purpose")
    budget = _settings(retrieval_budget)
    admitted = bf.admission(bank, journal, relationship)
    binding = bf.digest(
        {
            "source": source_binding,
            "admission": admitted,
            "purpose": purpose,
            "relationship": relationship,
            "retrieval": PROTOCOL,
            "budget": budget,
            "implementation_sha256": _implementation_digest(),
        }
    )
    index = EvidenceIndex(
        bank, journal, source_binding, relationship, budget["page_rows"]
    )
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    root = output / "bank-first-attempts"
    if output.is_symlink() or root.is_symlink():
        raise ValueError("Run storage cannot use symbolic links")
    for name in (
        "bank_first_state.json",
        "bank_first_state.json.new",
        "bank_first_admission.json",
        "bank_first_admission.json.new",
        "bank_first_result.json",
        "bank_first_result.json.new",
    ):
        if (output / name).is_symlink():
            raise ValueError("Run artifacts cannot use symbolic links")
    path = output / "bank_first_state.json"
    state: dict[str, Any] = (
        bf._read(path)
        if path.exists()
        else {
            "schema_version": bf.PROTOCOL,
            "binding_sha256": binding,
            "attempts": [],
            "groups": [],
            "stage_completed": {"luna": [], "sol": []},
            "errors": [],
        }
    )
    if state["binding_sha256"] != binding:
        raise ValueError(
            "Bank-first state belongs to different source/policy/purpose or retrieval budget"
        )
    if path.exists() and state.get("content_sha256") != bf.digest(
        {k: v for k, v in state.items() if k != "content_sha256"}
    ):
        raise ValueError("Retained state changed")
    groups, completed, pending_session = _reconstruct(
        index,
        state["attempts"],
        output,
        admitted,
        source_binding,
        relationship,
        purpose,
        budget,
        domain_validator,
    )
    if path.exists() and groups != state["groups"]:
        raise ValueError("Stored conclusions differ from verified replay")
    state["groups"], state["errors"] = groups, []
    bf._write(output / "bank_first_admission.json", admitted)
    stopped = False
    for stage in ("luna", "sol"):
        if stopped:
            break
        while focus := bf._next_focus(bank, groups, stage, completed[stage]):
            session = pending_session or _initial(index, focus, groups)
            pending_session = None
            failures = 0
            last_error = None
            while True:
                packet = _packet(
                    index,
                    session,
                    focus,
                    groups,
                    admitted,
                    source_binding,
                    relationship,
                    stage,
                    purpose,
                    budget,
                )
                existing = next(
                    (
                        a
                        for a in reversed(state["attempts"])
                        if a["status"] == "awaiting_native_host"
                        and a["packet_sha256"] == packet["packet_sha256"]
                    ),
                    None,
                )
                directory = root / (
                    existing["directory"]
                    if existing
                    else f"{len(state['attempts'])+1:05d}-{stage}"
                )
                directory.mkdir(parents=True, exist_ok=True)
                text, schema = bf.prompt(packet, last_error), bf.output_schema(packet)
                if existing:
                    if bf._read(directory / "packet.json") != packet:
                        raise ValueError("Pending request changed")
                    attempt = existing
                    text = (directory / "prompt.md").read_text()
                else:
                    attempt = {
                        "directory": directory.name,
                        "stage": stage,
                        "status": "started",
                        "packet_sha256": packet["packet_sha256"],
                        "format_attempt": failures + 1,
                        "bank_ids": sorted(i for f in focus for i in f["bank_ids"]),
                    }
                    state["attempts"].append(attempt)
                    bf._write(directory / "packet.json", packet)
                    bf._write(
                        directory / "worker_packet.json", bf.worker_packet(packet)
                    )
                    bf._write(
                        directory / "row_reference_map.json", bf.reference_map(packet)
                    )
                    bf._write(directory / "schema.json", schema)
                    (directory / "prompt.md").write_text(text)
                bf._save(path, state)
                received_response = False
                try:
                    _source_check(source_check)
                    size = len(text.encode()) + len(
                        json.dumps(schema, ensure_ascii=False).encode()
                    )
                    if (
                        size > budget["context_bytes"]
                        or len(text.encode()) > semantic.MAX_PROMPT_BYTES
                    ):
                        raise RetrievalLimit(
                            f"Working context {size} bytes exceeds configured/native budget ({budget['context_bytes']} / {semantic.MAX_PROMPT_BYTES}); no accounting conclusion"
                        )
                    if session["round"] > budget["max_rounds"]:
                        raise RetrievalLimit(
                            "Evidence-round budget exhausted; technical deferral"
                        )
                    selection = attempt.get("selection") or (
                        worker_selection
                        if stage == "luna" and worker_selection
                        else select(workflow_id=packet["workflow_id"], stage=stage)
                    )
                    if selection.get("cost_class") not in (
                        {"low", "standard"} if stage == "luna" else {"escalation"}
                    ):
                        raise RuntimeError("Wrong worker class for stage")
                    attempt["selection"] = dict(selection)
                    bf._save(path, state)
                    call = invoke(
                        prompt=text,
                        output_schema=schema,
                        output_dir=directory,
                        workflow_id=packet["workflow_id"],
                        packet_sha256=packet["packet_sha256"],
                        worker_selection=selection,
                        codex_bin=codex_bin,
                        source_records=[
                            source_projections.get(
                                r["transaction_id"],
                                {"record_id": r["transaction_id"], "fields": list(r)},
                            )
                            for r in packet["bank_records"] + packet["journal_records"]
                        ],
                    )
                    response = call["response_payload"]
                    received_response = True
                    receipt = bf._read(Path(call["launch_receipt"]))
                    bf._write(directory / "response.json", response)
                    bf._write(directory / "receipt.json", receipt)
                    bf.validate_receipt(
                        receipt, packet, response, text, schema, selection
                    )
                    attempt.update(
                        usage=call.get("usage"),
                        duration_ms=call.get("duration_ms"),
                        context_bytes=size,
                        requested_worker=receipt["requested_worker_configuration"],
                        observed_worker=receipt.get("runtime_attestation", {}),
                    )
                    _source_check(source_check)
                    if response.get("evidence_requests"):
                        if session["round"] >= budget["max_rounds"]:
                            raise RetrievalLimit(
                                "Evidence-round budget exhausted; technical deferral"
                            )
                        session = _advance(index, session, packet, response)
                        attempt["status"] = "evidence_requested"
                        last_error = None
                        failures = 0
                    else:
                        groups = _decide(packet, response, groups, domain_validator)
                        state["groups"] = groups
                        attempt["status"] = "validated"
                        completed[stage].update(
                            i
                            for g in bf.decode_response(
                                packet, {"groups": response["groups"]}
                            )["groups"]
                            for i in g["bank_ids"]
                        )
                        state["stage_completed"][stage] = sorted(completed[stage])
                except NativeWorkerPending:
                    attempt["status"] = "awaiting_native_host"
                    raise
                except (ValueError, semantic.WorkerResponseFormatError) as error:
                    failures += 1
                    last_error = str(error)[:2400]
                    status = (
                        "rejected_format"
                        if received_response
                        or isinstance(error, semantic.WorkerResponseFormatError)
                        else "technical_error"
                    )
                    attempt.update(status=status, error=str(error))
                    if status == "technical_error":
                        stopped = True
                    process_path = getattr(error, "process_receipt", None)
                    if process_path is not None:
                        process_receipt = bf._read(Path(process_path))
                        attempt.update(
                            usage=process_receipt.get("jsonl_observation", {}).get(
                                "usage"
                            ),
                            duration_ms=process_receipt.get("process", {}).get(
                                "duration_ms"
                            ),
                        )
                    if failures >= bf.policy()["format_attempts_per_stage"]:
                        stopped = True
                except (OSError, RuntimeError) as error:
                    attempt.update(status="technical_error", error=str(error))
                    stopped = True
                finally:
                    attempt["artifact_sha256"] = {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in directory.iterdir()
                        if p.is_file() and not p.is_symlink()
                    }
                    bf._save(path, state)
                if stopped:
                    state["errors"] = [
                        {
                            "stage": stage,
                            "bank_ids": attempt["bank_ids"],
                            "status": "error",
                            "reason": attempt["error"],
                        }
                    ]
                    bf._save(path, state)
                    break
                if attempt["status"] == "validated":
                    break
            if stopped:
                break
    result = {
        "schema_version": bf.PROTOCOL,
        "retrieval_protocol": PROTOCOL,
        "implementation_sha256": _implementation_digest(),
        "purpose": purpose,
        "retrieval_budget": budget,
        "source_binding": dict(source_binding),
        "binding_sha256": binding,
        "policy": bf.policy(),
        "admission_sha256": admitted["content_sha256"],
        "groups": groups,
        "attempts": state["attempts"],
        "errors": state["errors"],
        "summary": bf.summary(bank, groups, state["errors"], complete=not stopped),
        "questions": bf.question_items(groups),
        "system_conclusions_are_human_choices": False,
        "entries_posted": False,
        "retained_native_evidence": [],
    }
    for attempt in state["attempts"]:
        if attempt["status"] not in {"validated", "evidence_requested"}:
            continue
        d = root / attempt["directory"]
        result["retained_native_evidence"].append(
            {
                "attempt": attempt,
                **{
                    k: bf._read(d / (k + ".json"))
                    for k in ("packet", "schema", "response", "receipt")
                },
                "selection": attempt["selection"],
                "prompt": (d / "prompt.md").read_text(),
                "packet_json": (d / "packet.json").read_text(),
                "response_json": (d / "response.json").read_text(),
                "schema_json": (d / "schema.json").read_text(),
            }
        )
    result["content_sha256"] = bf.digest(result)
    bf._write(output / "bank_first_result.json", result)
    index.close()
    return result


def replay_result(result, bank, journal, relationship, *, domain_validator=None):
    """Replay every read request and decision against the original scoped index."""
    import tempfile

    if result.get("content_sha256") != bf.digest(
        {k: v for k, v in result.items() if k != "content_sha256"}
    ):
        raise ValueError("Retained result changed")
    if result.get("implementation_sha256") != _implementation_digest():
        raise ValueError(
            "Retrieval implementation changed; use original execution source for replay"
        )
    budget = _settings(result["retrieval_budget"])
    admitted = bf.admission(bank, journal, relationship)
    if admitted["content_sha256"] != result["admission_sha256"]:
        raise ValueError("Source population changed")
    index = EvidenceIndex(
        bank, journal, result["source_binding"], relationship, budget["page_rows"]
    )
    try:
        with tempfile.TemporaryDirectory(prefix="retrieval-replay-") as temp:
            root = Path(temp)
            attempts = []
            for evidence in result["retained_native_evidence"]:
                attempt = evidence["attempt"]
                if Path(attempt["directory"]).name != attempt["directory"]:
                    raise ValueError("Retained path escapes run")
                d = root / "bank-first-attempts" / attempt["directory"]
                d.mkdir(parents=True)
                for key in ("packet", "schema", "response", "receipt"):
                    raw = evidence.get(key + "_json")
                    if raw is not None:
                        if json.loads(raw) != evidence[key]:
                            raise ValueError("Retained serialization changed")
                        (d / (key + ".json")).write_text(raw)
                    else:
                        bf._write(d / (key + ".json"), evidence[key])
                if (
                    json.loads(evidence["response_json"]) != evidence["response"]
                    or json.loads(evidence["schema_json"]) != evidence["schema"]
                ):
                    raise ValueError("Retained serialization changed")
                (d / "prompt.md").write_text(evidence["prompt"])
                attempts.append(
                    {k: v for k, v in attempt.items() if k != "artifact_sha256"}
                )
            groups, _, _ = _reconstruct(
                index,
                attempts,
                root,
                admitted,
                result["source_binding"],
                relationship,
                result.get(
                    "purpose",
                    (
                        result["retained_native_evidence"][0]["packet"]["purpose"]
                        if attempts
                        else "bank_open_items"
                    ),
                ),
                budget,
                domain_validator,
            )
        if groups != result["groups"]:
            raise ValueError("Conclusions differ from native evidence")
        return groups
    finally:
        index.close()
