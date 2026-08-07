#!/usr/bin/env python3
"""Record and professionally dispose bounded Codex suggestions for one case."""

from __future__ import annotations

import argparse
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from case_core import (
    canonical_json_sha256,
    case_lock,
    iso_now,
    load_json_object,
    load_running_context,
    prohibited_secret_paths,
    require_run_artifact,
    safe_identifier,
    write_private_json,
)
from intelligence_contract import (
    COLLECTION_ID_FIELDS,
    IntelligenceTask,
    artifact_input_hashes,
    build_intelligence_packet,
    build_next_intelligence_packet,
    intelligence_packet_hash,
    validate_intelligence_output,
)
from schema_validation import validate_artifact_schema

__all__ = [
    "create_intelligence_packet",
    "decide_intelligence",
    "record_intelligence",
    "main",
]

LOGGER = logging.getLogger(__name__)
DECISIONS = {"accepted", "rejected", "returned"}
MAX_INTELLIGENCE_OUTPUT_BYTES = 2_000_000


def _artifacts(
    output_dir: Path, *, run_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    intake = require_run_artifact(output_dir / "case_intake.json", run_id=run_id)
    sources = require_run_artifact(output_dir / "source_register.json", run_id=run_id)
    workbench = require_run_artifact(
        output_dir / "application_workbench.json", run_id=run_id
    )
    register = require_run_artifact(
        output_dir / "intelligence_register.json", run_id=run_id
    )
    return intake, sources, workbench, register


def _require_schema(name: str, payload: dict[str, Any]) -> None:
    issues = validate_artifact_schema(name, payload)
    if issues:
        paths = ", ".join(str(issue["path"]) for issue in issues[:5])
        raise ValueError(f"{name} violates its schema: {paths}")


def _packet(
    intake: Mapping[str, Any],
    sources: Mapping[str, Any],
    workbench: Mapping[str, Any],
    *,
    task: IntelligenceTask | str | None,
    subject_ids: Sequence[str],
) -> dict[str, Any]:
    if task is None:
        if subject_ids:
            raise ValueError("subject_ids require an explicit intelligence task")
        return build_next_intelligence_packet(intake, sources, workbench)
    return build_intelligence_packet(intake, sources, workbench, task, subject_ids)


def create_intelligence_packet(
    *,
    output_dir: Path,
    client_engagement: Path,
    task: IntelligenceTask | str | None = None,
    subject_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Return bounded task context without mutating case state."""

    context = load_running_context(client_engagement, output_dir=output_dir)
    run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    with case_lock(output_dir):
        intake, sources, workbench, register = _artifacts(output_dir, run_id=run_id)
        for name, payload in (
            ("case_intake", intake),
            ("source_register", sources),
            ("application_workbench", workbench),
            ("intelligence_register", register),
        ):
            _require_schema(name, payload)
        return _packet(
            intake,
            sources,
            workbench,
            task=task,
            subject_ids=subject_ids,
        )


def record_intelligence(
    *,
    output_dir: Path,
    client_engagement: Path,
    model_output: Mapping[str, Any],
    provider: str,
    model: str,
    prompt_template_version: str,
    recorded_by: str,
    idempotency_key: str,
    task: IntelligenceTask | str | None = None,
    subject_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Seal a model response as MODEL_SUGGESTED; never apply it implicitly."""

    metadata = {
        "provider": str(provider or "").strip(),
        "model": str(model or "").strip(),
        "prompt_template_version": str(prompt_template_version or "").strip(),
    }
    if not all(metadata.values()):
        raise ValueError(
            "exact provider, model, and prompt template version are required"
        )
    recorded_by = safe_identifier(recorded_by, field="recorded_by")
    idempotency_key = safe_identifier(idempotency_key, field="idempotency_key")
    encoded_output = json.dumps(
        model_output, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(encoded_output) > MAX_INTELLIGENCE_OUTPUT_BYTES:
        raise ValueError("model output exceeds the bounded intelligence record size")
    secret_paths = prohibited_secret_paths(model_output, path="model_output")
    if secret_paths:
        raise ValueError(
            "model output contains prohibited secret/session fields: "
            + ", ".join(secret_paths)
        )
    context = load_running_context(client_engagement, output_dir=output_dir)
    run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    with case_lock(output_dir):
        intake, sources, workbench, register = _artifacts(output_dir, run_id=run_id)
        packet = _packet(
            intake,
            sources,
            workbench,
            task=task,
            subject_ids=subject_ids,
        )
        normalized = validate_intelligence_output(packet, model_output)
        runs = register.get("runs")
        if not isinstance(runs, list):
            raise ValueError("intelligence register runs must be a list")
        repeated = [
            item
            for item in runs
            if isinstance(item, dict) and item.get("idempotency_key") == idempotency_key
        ]
        if repeated:
            if len(repeated) != 1:
                raise ValueError("intelligence idempotency key is duplicated")
            prior = repeated[0]
            expected_retry = {
                "task": packet["task"],
                "subject_ids": packet["subject_ids"],
                "packet_sha256": intelligence_packet_hash(packet),
                "input_artifact_hashes": artifact_input_hashes(
                    intake, sources, workbench
                ),
                "model_metadata": metadata,
                "output": normalized,
                "recorded_by": recorded_by,
            }
            if any(prior.get(key) != value for key, value in expected_retry.items()):
                raise ValueError(
                    "idempotency key was already used for another response"
                )
            return deepcopy(prior)
        event = {
            "intelligence_run_id": f"INTEL-{len(runs) + 1:06d}",
            "idempotency_key": idempotency_key,
            "task": packet["task"],
            "subject_ids": packet["subject_ids"],
            "status": "MODEL_SUGGESTED",
            "packet_sha256": intelligence_packet_hash(packet),
            "input_artifact_hashes": artifact_input_hashes(intake, sources, workbench),
            "model_metadata": metadata,
            "output": normalized,
            "recorded_by": recorded_by,
            "recorded_at": iso_now(),
            "requires_review": True,
            "decision": None,
            "applied_workbench_sha256": None,
        }
        runs.append(event)
        _require_schema("intelligence_register", register)
        write_private_json(output_dir / "intelligence_register.json", register)
    return deepcopy(event)


def _run_by_id(register: dict[str, Any], run_id: str) -> dict[str, Any]:
    matching = [
        item
        for item in register.get("runs", [])
        if isinstance(item, dict) and item.get("intelligence_run_id") == run_id
    ]
    if len(matching) != 1:
        raise ValueError("intelligence run does not exist or is duplicated")
    return matching[0]


def _existing_ids(workbench: Mapping[str, Any]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for collection, field in COLLECTION_ID_FIELDS.items():
        if field is None:
            items = workbench.get("authority_simulation", {}).get("checks", [])
            field = "check_id"
        else:
            items = workbench.get(collection, [])
        for item in items:
            if isinstance(item, Mapping):
                identifier = str(item.get(field) or "")
                if identifier:
                    if identifier in owners:
                        raise ValueError(
                            "workbench contains cross-collection duplicate IDs"
                        )
                    owners[identifier] = collection
    return owners


def _proposal_references(value: object, *, key: str = "") -> set[str]:
    references: set[str] = set()
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            references.update(_proposal_references(child, key=str(child_key)))
    elif isinstance(value, list):
        for child in value:
            references.update(_proposal_references(child, key=key))
    elif key in {
        "requirement_id",
        "requirement_ids",
        "source_id",
        "fact_ids",
        "source_ids",
        "material_source_ids",
        "related_ids",
    }:
        text = str(value or "").strip()
        if text:
            references.add(text)
    return references


def _candidate_workbench(
    workbench: Mapping[str, Any],
    output: Mapping[str, Any],
    *,
    source_ids: set[str],
) -> dict[str, Any]:
    candidate = deepcopy(dict(workbench))
    existing = _existing_ids(candidate)
    recommendations = list(output.get("recommendations", []))
    proposed_ids = {
        str(item.get("target_id"))
        for item in recommendations
        if item.get("action") == "CREATE"
    }
    if len(proposed_ids) != sum(
        item.get("action") == "CREATE" for item in recommendations
    ):
        raise ValueError("one decision cannot create duplicate target IDs")
    allowed_references = set(existing) | source_ids | proposed_ids
    for recommendation in recommendations:
        action = recommendation.get("action")
        if action == "GUIDANCE":
            continue
        collection = str(recommendation.get("target_collection"))
        target_id = str(recommendation.get("target_id"))
        payload = deepcopy(recommendation.get("proposed_payload"))
        unknown_refs = _proposal_references(payload) - allowed_references
        if unknown_refs:
            raise ValueError(
                "proposal contains references outside current case state: "
                + ", ".join(sorted(unknown_refs))
            )
        if collection == "authority_simulation":
            current = candidate[collection]
            if action != "UPDATE" or target_id != "authority_simulation":
                raise ValueError(
                    "authority simulation must replace its singleton by UPDATE"
                )
            if current.get("status") == "reviewed" or any(
                item.get("review_status") == "confirmed"
                for item in current.get("checks", [])
            ):
                raise ValueError(
                    "model output cannot overwrite reviewed authority work"
                )
            candidate[collection] = payload
            continue
        field = COLLECTION_ID_FIELDS[collection]
        items = candidate[collection]
        matching = [
            index for index, item in enumerate(items) if item.get(field) == target_id
        ]
        if action == "CREATE":
            if target_id in existing or target_id in source_ids:
                raise ValueError("model output cannot create an existing target ID")
            items.append(payload)
            existing[target_id] = collection
        elif action == "UPDATE":
            if len(matching) != 1:
                raise ValueError("model update target must exist exactly once")
            current = items[matching[0]]
            if current.get("review_status") in {"confirmed", "blocked"}:
                raise ValueError(
                    "model output cannot overwrite confirmed or blocked work"
                )
            items[matching[0]] = payload
        else:
            raise ValueError("unsupported recommendation action")
    candidate_ids = _existing_ids(candidate)
    collisions = set(candidate_ids) & source_ids
    if collisions:
        raise ValueError(
            "proposal collides with source IDs: " + ", ".join(sorted(collisions))
        )
    _require_schema("application_workbench", candidate)
    return candidate


def _decision_record(
    decision: str,
    *,
    reviewer_id: str,
    reviewer_role: str,
    notes: str,
    candidate_hash: str | None,
) -> dict[str, Any]:
    return {
        "decision": decision,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "confirmation_basis": "explicit_user_confirmation",
        "identity_assurance": "asserted_not_authenticated",
        "decided_at": iso_now(),
        "notes": notes.strip(),
        "candidate_workbench_sha256": candidate_hash,
    }


def decide_intelligence(
    *,
    output_dir: Path,
    client_engagement: Path,
    intelligence_run_id: str,
    decision: str,
    reviewer_id: str,
    reviewer_role: str,
    confirmed_by_user: bool,
    notes: str = "",
) -> dict[str, Any]:
    """Accept, reject, or return one exact suggestion after explicit review."""

    intelligence_run_id = safe_identifier(
        intelligence_run_id, field="intelligence_run_id"
    )
    reviewer_id = safe_identifier(reviewer_id, field="reviewer_id")
    decision = str(decision or "").strip().lower()
    reviewer_role = str(reviewer_role or "").strip()
    if decision not in DECISIONS:
        raise ValueError("unsupported intelligence decision")
    if not reviewer_role:
        raise ValueError("reviewer_role is required")
    if confirmed_by_user is not True:
        raise ValueError("explicit user confirmation is required")
    context = load_running_context(client_engagement, output_dir=output_dir)
    case_run_id = safe_identifier(context["run_id"], field="run_id")
    output_dir = output_dir.resolve()
    with case_lock(output_dir):
        intake, sources, workbench, register = _artifacts(
            output_dir, run_id=case_run_id
        )
        run = _run_by_id(register, intelligence_run_id)
        if run.get("status") in {"ACCEPTED", "REJECTED", "RETURNED"}:
            prior = run.get("decision") or {}
            if prior.get("decision") == decision:
                return deepcopy(run)
            raise ValueError("intelligence run already has a final decision")
        current_hashes = artifact_input_hashes(intake, sources, workbench)
        if run.get("status") == "APPLYING":
            expected = run.get("decision", {}).get("candidate_workbench_sha256")
            current_workbench_hash = canonical_json_sha256(workbench)
            if decision != "accepted":
                raise ValueError("interrupted apply can only resume acceptance")
            original_hashes = run.get("input_artifact_hashes", {})
            current_non_workbench = {
                key: value
                for key, value in current_hashes.items()
                if key != "application_workbench"
            }
            original_non_workbench = {
                key: value
                for key, value in original_hashes.items()
                if key != "application_workbench"
            }
            if current_non_workbench != original_non_workbench:
                raise ValueError(
                    "interrupted apply inputs changed outside the workbench"
                )
            if expected != current_workbench_hash:
                if current_workbench_hash != original_hashes.get(
                    "application_workbench"
                ):
                    raise ValueError(
                        "interrupted apply found neither original nor candidate workbench"
                    )
                source_ids = {
                    str(item.get("source_id")) for item in sources.get("sources", [])
                }
                candidate = _candidate_workbench(
                    workbench, run["output"], source_ids=source_ids
                )
                if canonical_json_sha256(candidate) != expected:
                    raise ValueError("interrupted apply candidate is not reproducible")
                write_private_json(output_dir / "application_workbench.json", candidate)
                current_workbench_hash = expected
            run["status"] = "ACCEPTED"
            run["applied_workbench_sha256"] = current_workbench_hash
            _require_schema("intelligence_register", register)
            write_private_json(output_dir / "intelligence_register.json", register)
            return deepcopy(run)
        if run.get("status") == "STALE":
            raise ValueError("stale intelligence must be rerun from current case state")
        if run.get("status") != "MODEL_SUGGESTED":
            raise ValueError("intelligence run is not reviewable")
        if run.get("input_artifact_hashes") != current_hashes:
            run["status"] = "STALE"
            _require_schema("intelligence_register", register)
            write_private_json(output_dir / "intelligence_register.json", register)
            raise ValueError("case inputs changed; intelligence run was marked STALE")
        if decision in {"rejected", "returned"}:
            run["status"] = decision.upper()
            run["decision"] = _decision_record(
                decision,
                reviewer_id=reviewer_id,
                reviewer_role=reviewer_role,
                notes=notes,
                candidate_hash=None,
            )
            _require_schema("intelligence_register", register)
            write_private_json(output_dir / "intelligence_register.json", register)
            return deepcopy(run)
        source_ids = {str(item.get("source_id")) for item in sources.get("sources", [])}
        candidate = _candidate_workbench(
            workbench, run["output"], source_ids=source_ids
        )
        candidate_hash = canonical_json_sha256(candidate)
        run["status"] = "APPLYING"
        run["decision"] = _decision_record(
            "accepted",
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            notes=notes,
            candidate_hash=candidate_hash,
        )
        _require_schema("intelligence_register", register)
        write_private_json(output_dir / "intelligence_register.json", register)
        write_private_json(output_dir / "application_workbench.json", candidate)
        run["status"] = "ACCEPTED"
        run["applied_workbench_sha256"] = candidate_hash
        _require_schema("intelligence_register", register)
        write_private_json(output_dir / "intelligence_register.json", register)
    return deepcopy(run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--client-engagement", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    packet_parser = subparsers.add_parser("packet")
    packet_parser.add_argument(
        "--task", choices=[item.value for item in IntelligenceTask]
    )
    packet_parser.add_argument("--subject-id", action="append", default=[])
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--model-output", required=True, type=Path)
    record_parser.add_argument("--provider", required=True)
    record_parser.add_argument("--model", required=True)
    record_parser.add_argument("--prompt-template-version", required=True)
    record_parser.add_argument("--recorded-by", required=True)
    record_parser.add_argument("--idempotency-key", required=True)
    record_parser.add_argument(
        "--task", choices=[item.value for item in IntelligenceTask]
    )
    record_parser.add_argument("--subject-id", action="append", default=[])
    decide_parser = subparsers.add_parser("decide")
    decide_parser.add_argument("--intelligence-run-id", required=True)
    decide_parser.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    decide_parser.add_argument("--reviewer-id", required=True)
    decide_parser.add_argument("--reviewer-role", required=True)
    decide_parser.add_argument("--confirmed-by-user", action="store_true")
    decide_parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    common = {
        "output_dir": args.output_dir,
        "client_engagement": args.client_engagement,
    }
    if args.command == "packet":
        payload = create_intelligence_packet(
            **common, task=args.task, subject_ids=args.subject_id
        )
    elif args.command == "record":
        payload = record_intelligence(
            **common,
            model_output=load_json_object(args.model_output),
            provider=args.provider,
            model=args.model,
            prompt_template_version=args.prompt_template_version,
            recorded_by=args.recorded_by,
            idempotency_key=args.idempotency_key,
            task=args.task,
            subject_ids=args.subject_id,
        )
    else:
        payload = decide_intelligence(
            **common,
            intelligence_run_id=args.intelligence_run_id,
            decision=args.decision,
            reviewer_id=args.reviewer_id,
            reviewer_role=args.reviewer_role,
            confirmed_by_user=args.confirmed_by_user,
            notes=args.notes,
        )
    LOGGER.info("%s", json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
