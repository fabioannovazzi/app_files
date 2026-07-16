"""Deterministically shard and merge Attribute Reporting mapping artifacts.

The deterministic boundary is intentionally mechanical: this module partitions
already-prepared tasks, pins exact content, and enforces complete merge coverage.
Codex agents remain responsible for every semantic mapping and review judgment.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from attribute_reporting import ContractError, validate_mapping_payloads

__all__ = [
    "MappingShardError",
    "merge_mapping_decisions",
    "merge_mapping_review",
    "shard_mapping_review",
    "shard_mapping_tasks",
]

LOGGER = logging.getLogger(__name__)

MAPPING_TASK_SCHEMA = "attribute_reporting.mapping_tasks.v1"
MAPPING_DECISION_SCHEMA = "attribute_reporting.mapping_decisions.v1"
MAPPING_REVIEW_SCHEMA = "attribute_reporting.mapping_review.v1"
TASK_MANIFEST_SCHEMA = "attribute_reporting.mapping_task_shard_manifest.v1"
TASK_SHARD_SCHEMA = "attribute_reporting.mapping_task_shard.v1"
DECISION_COORDINATION_SCHEMA = "attribute_reporting.mapping_decision_coordination.v1"
REVIEW_MANIFEST_SCHEMA = "attribute_reporting.mapping_review_shard_manifest.v1"
REVIEW_SHARD_SCHEMA = "attribute_reporting.mapping_review_shard.v1"
REVIEW_COORDINATION_SCHEMA = "attribute_reporting.mapping_review_coordination.v1"
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_REVIEW_VERDICTS = {
    "supported",
    "supported_with_caveat",
    "unsupported",
    "unable_to_determine",
}


class MappingShardError(ValueError):
    """Raised when a shard or merge artifact violates its exact contract."""


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MappingShardError(f"Required JSON file is missing: {source}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MappingShardError(f"Invalid JSON in {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MappingShardError(f"Expected a JSON object in {source}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    temporary = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
        temporary_path.chmod(0o600)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _require_safe_id(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not SAFE_ID_RE.fullmatch(normalized):
        raise MappingShardError(f"{label} is missing or invalid: {normalized!r}")
    return normalized


def _require_sha256(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not SHA256_RE.fullmatch(normalized):
        raise MappingShardError(f"{label} is not a lowercase SHA-256 digest")
    return normalized


def _require_positive_bound(value: int, *, label: str) -> None:
    if value <= 0:
        raise MappingShardError(f"{label} must be greater than zero")


def _task_records(tasks: Mapping[str, Any]) -> list[dict[str, Any]]:
    if tasks.get("schema_version") != MAPPING_TASK_SCHEMA:
        raise MappingShardError("Unsupported mapping task schema")
    taxonomy = tasks.get("taxonomy_snapshot")
    scope = tasks.get("scope")
    coverage = tasks.get("coverage")
    records = tasks.get("tasks")
    if not isinstance(taxonomy, dict):
        raise MappingShardError("Mapping tasks require a taxonomy_snapshot object")
    _require_safe_id(taxonomy.get("version"), label="Taxonomy version")
    _require_sha256(taxonomy.get("sha256"), label="Taxonomy snapshot sha256")
    if not isinstance(scope, dict):
        raise MappingShardError("Mapping tasks require a source scope object")
    if not isinstance(coverage, dict) or coverage.get("truncated") is not False:
        raise MappingShardError(
            "Only a complete, non-truncated mapping workset may be sharded"
        )
    if not isinstance(records, list):
        raise MappingShardError("Mapping tasks must contain a tasks list")
    if coverage.get("task_count") != len(records) or coverage.get(
        "task_count_before_limit"
    ) != len(records):
        raise MappingShardError(
            "Complete mapping coverage counts do not match the tasks list"
        )

    task_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise MappingShardError("Each mapping task must be an object")
        task_id = _require_safe_id(record.get("task_id"), label="Mapping task id")
        if task_id in task_ids:
            raise MappingShardError(f"Duplicate mapping task id: {task_id!r}")
        product = record.get("product")
        if not isinstance(product, dict):
            raise MappingShardError(f"Mapping task {task_id} has no product object")
        _require_sha256(
            product.get("source_row_sha256"),
            label=f"Mapping task {task_id} source-row sha256",
        )
        task_ids.add(task_id)
        normalized.append(copy.deepcopy(record))
    return normalized


def _chunked(
    records: Sequence[dict[str, Any]], bound: int
) -> list[list[dict[str, Any]]]:
    return [
        list(records[index : index + bound]) for index in range(0, len(records), bound)
    ]


def _task_shard_contract(
    tasks: Mapping[str, Any],
    *,
    max_tasks_per_shard: int,
) -> tuple[dict[str, Any], list[list[dict[str, Any]]]]:
    _require_positive_bound(max_tasks_per_shard, label="max_tasks_per_shard")
    records = _task_records(tasks)
    chunks = _chunked(records, max_tasks_per_shard)
    assignments = [
        {
            "index": index,
            "task_ids": [str(task["task_id"]) for task in chunk],
            "task_sha256s": {
                str(task["task_id"]): _canonical_sha256(task) for task in chunk
            },
        }
        for index, chunk in enumerate(chunks, start=1)
    ]
    contract = {
        "schema_version": TASK_SHARD_SCHEMA,
        "source_tasks_sha256": _canonical_sha256(tasks),
        "source_taxonomy_snapshot_sha256": _canonical_sha256(
            tasks["taxonomy_snapshot"]
        ),
        "source_scope_sha256": _canonical_sha256(tasks["scope"]),
        "source_coverage_sha256": _canonical_sha256(tasks["coverage"]),
        "task_count": len(records),
        "max_tasks_per_shard": max_tasks_per_shard,
        "assignments": assignments,
    }
    return contract, chunks


def _task_shard_payload(
    tasks: Mapping[str, Any],
    *,
    chunk: Sequence[dict[str, Any]],
    index: int,
    total: int,
    manifest_id: str,
    contract_sha256: str,
) -> dict[str, Any]:
    payload = copy.deepcopy(dict(tasks))
    source_coverage = copy.deepcopy(dict(tasks["coverage"]))
    payload["coverage"] = {
        **source_coverage,
        "task_count_before_limit": int(source_coverage["task_count"]),
        "task_count": len(chunk),
        "truncated": len(chunk) < int(source_coverage["task_count"]),
        "shard_slice": True,
    }
    payload["tasks"] = copy.deepcopy(list(chunk))
    width = max(4, len(str(total)))
    shard_id = f"mapping-task-shard-{index:0{width}d}-of-{total:0{width}d}"
    payload["shard"] = {
        "schema_version": TASK_SHARD_SCHEMA,
        "manifest_id": manifest_id,
        "contract_sha256": contract_sha256,
        "shard_id": shard_id,
        "index": index,
        "total": total,
        "source_tasks_sha256": _canonical_sha256(tasks),
        "source_coverage_sha256": _canonical_sha256(tasks["coverage"]),
        "task_ids": [str(task["task_id"]) for task in chunk],
        "task_sha256s": {
            str(task["task_id"]): _canonical_sha256(task) for task in chunk
        },
    }
    return payload


def _build_task_shards(
    tasks: Mapping[str, Any],
    *,
    max_tasks_per_shard: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    contract, chunks = _task_shard_contract(
        tasks,
        max_tasks_per_shard=max_tasks_per_shard,
    )
    contract_sha256 = _canonical_sha256(contract)
    manifest_id = f"mapping-task-shards-{contract_sha256[:24]}"
    total = len(chunks)
    slices = [
        _task_shard_payload(
            tasks,
            chunk=chunk,
            index=index,
            total=total,
            manifest_id=manifest_id,
            contract_sha256=contract_sha256,
        )
        for index, chunk in enumerate(chunks, start=1)
    ]
    manifest_shards: list[dict[str, Any]] = []
    for task_slice in slices:
        shard = task_slice["shard"]
        shard_id = str(shard["shard_id"])
        manifest_shards.append(
            {
                "shard_id": shard_id,
                "index": shard["index"],
                "task_count": len(task_slice["tasks"]),
                "task_ids": list(shard["task_ids"]),
                "task_sha256s": dict(shard["task_sha256s"]),
                "task_slice_file": f"{shard_id}.json",
                "task_slice_sha256": _canonical_sha256(task_slice),
                "decision_template_file": f"{shard_id}.decisions.json",
            }
        )
    stable_manifest = {
        "schema_version": TASK_MANIFEST_SCHEMA,
        "manifest_id": manifest_id,
        "contract_sha256": contract_sha256,
        "source_tasks_sha256": contract["source_tasks_sha256"],
        "source_taxonomy_snapshot_sha256": contract["source_taxonomy_snapshot_sha256"],
        "source_scope_sha256": contract["source_scope_sha256"],
        "source_coverage_sha256": contract["source_coverage_sha256"],
        "task_count": contract["task_count"],
        "max_tasks_per_shard": max_tasks_per_shard,
        "shard_count": total,
        "shards": manifest_shards,
    }
    manifest = {
        **stable_manifest,
        "manifest_sha256": _canonical_sha256(stable_manifest),
    }
    decision_templates = [
        {
            "schema_version": MAPPING_DECISION_SCHEMA,
            "taxonomy_snapshot": copy.deepcopy(tasks["taxonomy_snapshot"]),
            "agent": {
                "execution": "codex_agent",
                "agent_id": "",
            },
            "shard": {
                "schema_version": TASK_SHARD_SCHEMA,
                "manifest_id": manifest_id,
                "manifest_sha256": manifest["manifest_sha256"],
                "contract_sha256": contract_sha256,
                "shard_id": str(task_slice["shard"]["shard_id"]),
                "source_tasks_sha256": contract["source_tasks_sha256"],
                "source_task_slice_sha256": manifest_shards[index]["task_slice_sha256"],
                "task_ids": list(task_slice["shard"]["task_ids"]),
                "task_sha256s": dict(task_slice["shard"]["task_sha256s"]),
            },
            "decisions": [],
        }
        for index, task_slice in enumerate(slices)
    ]
    return manifest, slices, decision_templates


def shard_mapping_tasks(
    tasks_path: Path,
    output_dir: Path,
    *,
    max_tasks_per_shard: int,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Write bounded task slices, decision templates, and an exact manifest."""

    tasks = _load_json(tasks_path)
    manifest, slices, decision_templates = _build_task_shards(
        tasks,
        max_tasks_per_shard=max_tasks_per_shard,
    )
    destination = output_dir.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    target_manifest = (
        manifest_path.expanduser().resolve()
        if manifest_path is not None
        else destination / "mapping_task_shards.json"
    )
    if target_manifest.parent != destination:
        raise MappingShardError(
            "Mapping task manifest must be written beside its shard files"
        )
    for manifest_shard, task_slice, decision_template in zip(
        manifest["shards"],
        slices,
        decision_templates,
    ):
        _write_json(destination / manifest_shard["task_slice_file"], task_slice)
        _write_json(
            destination / manifest_shard["decision_template_file"],
            decision_template,
        )
    _write_json(target_manifest, manifest)
    return manifest


def _validated_task_manifest(
    tasks: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    manifest_dir: Path,
) -> dict[str, Any]:
    if manifest.get("schema_version") != TASK_MANIFEST_SCHEMA:
        raise MappingShardError("Unsupported mapping task shard manifest schema")
    raw_bound = manifest.get("max_tasks_per_shard")
    if not isinstance(raw_bound, int):
        raise MappingShardError("Task shard manifest has no integer shard bound")
    expected, expected_slices, _templates = _build_task_shards(
        tasks,
        max_tasks_per_shard=raw_bound,
    )
    if dict(manifest) != expected:
        raise MappingShardError(
            "Mapping task shard manifest is stale or differs from its source tasks"
        )
    for item, expected_slice in zip(expected["shards"], expected_slices):
        actual_slice = _load_json(manifest_dir / str(item["task_slice_file"]))
        if actual_slice != expected_slice:
            raise MappingShardError(
                f"Mapping task slice {item['shard_id']} is stale or was modified"
            )
    return expected


def _expected_decision_shard(
    manifest: Mapping[str, Any],
    manifest_shard: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": TASK_SHARD_SCHEMA,
        "manifest_id": manifest["manifest_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "contract_sha256": manifest["contract_sha256"],
        "shard_id": manifest_shard["shard_id"],
        "source_tasks_sha256": manifest["source_tasks_sha256"],
        "source_task_slice_sha256": manifest_shard["task_slice_sha256"],
        "task_ids": list(manifest_shard["task_ids"]),
        "task_sha256s": dict(manifest_shard["task_sha256s"]),
    }


def _codex_agent(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("execution") != "codex_agent":
        raise MappingShardError(f"{label} must be attributed to a Codex agent")
    _require_safe_id(payload.get("agent_id"), label=f"{label} agent_id")
    return copy.deepcopy(payload)


def merge_mapping_decisions(
    tasks_path: Path,
    manifest_path: Path,
    decision_paths: Sequence[Path],
    output_path: Path,
    *,
    coordinator_agent_id: str,
) -> dict[str, Any]:
    """Merge exact decision shards without making any semantic judgment."""

    coordinator = _require_safe_id(
        coordinator_agent_id,
        label="Mapping coordinator agent_id",
    )
    tasks = _load_json(tasks_path)
    task_records = _task_records(tasks)
    manifest_source = manifest_path.expanduser().resolve()
    manifest = _validated_task_manifest(
        tasks,
        _load_json(manifest_source),
        manifest_dir=manifest_source.parent,
    )
    expected_by_shard = {str(item["shard_id"]): item for item in manifest["shards"]}
    contribution_by_shard: dict[str, dict[str, Any]] = {}
    decision_by_task: dict[str, dict[str, Any]] = {}
    for decision_path in decision_paths:
        partial = _load_json(decision_path)
        if partial.get("schema_version") != MAPPING_DECISION_SCHEMA:
            raise MappingShardError("Unsupported partial mapping decision schema")
        if partial.get("taxonomy_snapshot") != tasks["taxonomy_snapshot"]:
            raise MappingShardError(
                "Partial mapping decisions target a stale taxonomy snapshot"
            )
        raw_shard = partial.get("shard")
        if not isinstance(raw_shard, dict):
            raise MappingShardError("Partial mapping decisions have no shard pins")
        shard_id = str(raw_shard.get("shard_id") or "")
        expected_manifest_shard = expected_by_shard.get(shard_id)
        if expected_manifest_shard is None:
            raise MappingShardError(
                f"Partial mapping decisions reference an unknown shard: {shard_id!r}"
            )
        if shard_id in contribution_by_shard:
            raise MappingShardError(f"Duplicate mapping decision shard: {shard_id}")
        expected_shard = _expected_decision_shard(
            manifest,
            expected_manifest_shard,
        )
        if raw_shard != expected_shard:
            raise MappingShardError(
                f"Partial mapping decisions have stale shard pins: {shard_id}"
            )
        contributor = _codex_agent(
            partial.get("agent"),
            label=f"Mapping contributor for {shard_id}",
        )
        raw_decisions = partial.get("decisions")
        if not isinstance(raw_decisions, list):
            raise MappingShardError(
                f"Partial mapping decisions for {shard_id} require a decisions list"
            )
        allowed_task_ids = set(expected_manifest_shard["task_ids"])
        local_decisions: dict[str, dict[str, Any]] = {}
        for decision in raw_decisions:
            if not isinstance(decision, dict):
                raise MappingShardError(
                    "Each partial mapping decision must be an object"
                )
            task_id = str(decision.get("task_id") or "")
            if task_id not in allowed_task_ids:
                raise MappingShardError(
                    f"Mapping decision task {task_id!r} falls outside shard {shard_id}"
                )
            if task_id in local_decisions or task_id in decision_by_task:
                raise MappingShardError(
                    f"Duplicate mapping decision task id: {task_id!r}"
                )
            attributed_decision = copy.deepcopy(decision)
            attributed_decision["contributor_agent_id"] = str(contributor["agent_id"])
            attributed_decision["mapping_shard_id"] = shard_id
            local_decisions[task_id] = attributed_decision
        if set(local_decisions) != allowed_task_ids:
            missing = sorted(allowed_task_ids - set(local_decisions))
            raise MappingShardError(
                f"Mapping decision shard {shard_id} does not cover every task: "
                f"missing={missing}"
            )
        decision_by_task.update(local_decisions)
        artifact_sha256 = _canonical_sha256(partial)
        contribution_by_shard[shard_id] = {
            "shard_id": shard_id,
            "agent": contributor,
            "task_ids": list(expected_manifest_shard["task_ids"]),
            "decision_count": len(local_decisions),
            "artifact_sha256": artifact_sha256,
        }

    missing_shards = sorted(set(expected_by_shard) - set(contribution_by_shard))
    if missing_shards:
        raise MappingShardError(
            f"Mapping decisions are missing required shards: {missing_shards}"
        )
    source_task_ids = [str(task["task_id"]) for task in task_records]
    if set(decision_by_task) != set(source_task_ids):
        missing = sorted(set(source_task_ids) - set(decision_by_task))
        raise MappingShardError(
            f"Merged mapping decisions do not cover every source task: missing={missing}"
        )
    contributions = [
        contribution_by_shard[str(item["shard_id"])] for item in manifest["shards"]
    ]
    merged = {
        "schema_version": MAPPING_DECISION_SCHEMA,
        "taxonomy_snapshot": copy.deepcopy(tasks["taxonomy_snapshot"]),
        "agent": {
            "execution": "codex_agent",
            "agent_id": coordinator,
            "role": "mapping_shard_coordinator",
        },
        "coordination": {
            "schema_version": DECISION_COORDINATION_SCHEMA,
            "mode": "exact_shard_merge",
            "manifest_id": manifest["manifest_id"],
            "manifest_sha256": manifest["manifest_sha256"],
            "source_tasks_sha256": manifest["source_tasks_sha256"],
            "coordinator_agent_id": coordinator,
            "contribution_count": len(contributions),
            "contributions": contributions,
        },
        "decisions": [decision_by_task[task_id] for task_id in source_task_ids],
    }
    try:
        validate_mapping_payloads(tasks, merged)
    except ContractError as exc:
        raise MappingShardError(
            f"Merged mapping decisions violate the mapping contract: {exc}"
        ) from exc
    _write_json(output_path, merged)
    return merged


def _review_records(review: Mapping[str, Any]) -> list[dict[str, Any]]:
    if review.get("schema_version") != MAPPING_REVIEW_SCHEMA:
        raise MappingShardError("Unsupported mapping review schema")
    _require_safe_id(review.get("review_id"), label="Mapping review_id")
    _require_safe_id(review.get("author_agent_id"), label="Mapping author agent_id")
    if not isinstance(review.get("targets"), dict):
        raise MappingShardError("Mapping review requires exact global targets")
    raw_reviews = review.get("task_reviews")
    if not isinstance(raw_reviews, list):
        raise MappingShardError("Mapping review requires a task_reviews list")
    task_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    for item in raw_reviews:
        if not isinstance(item, dict):
            raise MappingShardError("Each mapping task review must be an object")
        task_id = _require_safe_id(item.get("task_id"), label="Review task id")
        if task_id in task_ids:
            raise MappingShardError(f"Duplicate review task id: {task_id!r}")
        if not isinstance(item.get("targets"), dict):
            raise MappingShardError(
                f"Mapping review task {task_id} requires exact content targets"
            )
        task_ids.add(task_id)
        records.append(copy.deepcopy(item))
    return records


def _review_shard_contract(
    review: Mapping[str, Any],
    *,
    max_reviews_per_shard: int,
) -> tuple[dict[str, Any], list[list[dict[str, Any]]]]:
    _require_positive_bound(max_reviews_per_shard, label="max_reviews_per_shard")
    records = _review_records(review)
    chunks = _chunked(records, max_reviews_per_shard)
    assignments = [
        {
            "index": index,
            "task_ids": [str(item["task_id"]) for item in chunk],
            "task_review_template_sha256s": {
                str(item["task_id"]): _canonical_sha256(item) for item in chunk
            },
        }
        for index, chunk in enumerate(chunks, start=1)
    ]
    contract = {
        "schema_version": REVIEW_SHARD_SCHEMA,
        "source_review_template_sha256": _canonical_sha256(review),
        "review_id": review["review_id"],
        "author_agent_id": review["author_agent_id"],
        "global_targets_sha256": _canonical_sha256(review["targets"]),
        "task_review_count": len(records),
        "max_reviews_per_shard": max_reviews_per_shard,
        "assignments": assignments,
    }
    return contract, chunks


def _build_review_shards(
    review: Mapping[str, Any],
    *,
    max_reviews_per_shard: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract, chunks = _review_shard_contract(
        review,
        max_reviews_per_shard=max_reviews_per_shard,
    )
    contract_sha256 = _canonical_sha256(contract)
    manifest_id = f"mapping-review-shards-{contract_sha256[:24]}"
    total = len(chunks)
    width = max(4, len(str(total)))
    slices: list[dict[str, Any]] = []
    manifest_shards: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        shard_id = f"mapping-review-shard-{index:0{width}d}-of-{total:0{width}d}"
        shard_pin = {
            "schema_version": REVIEW_SHARD_SCHEMA,
            "manifest_id": manifest_id,
            "contract_sha256": contract_sha256,
            "shard_id": shard_id,
            "index": index,
            "total": total,
            "source_review_template_sha256": contract["source_review_template_sha256"],
            "task_ids": [str(item["task_id"]) for item in chunk],
            "task_review_template_sha256s": {
                str(item["task_id"]): _canonical_sha256(item) for item in chunk
            },
        }
        partial = copy.deepcopy(dict(review))
        partial["overall_verdict"] = "unable_to_determine"
        partial["summary"] = "Complete the independent semantic reviews in this shard."
        partial["task_reviews"] = copy.deepcopy(list(chunk))
        partial["shard"] = shard_pin
        slices.append(partial)
        manifest_shards.append(
            {
                "shard_id": shard_id,
                "index": index,
                "task_review_count": len(chunk),
                "task_ids": list(shard_pin["task_ids"]),
                "task_review_template_sha256s": dict(
                    shard_pin["task_review_template_sha256s"]
                ),
                "review_slice_file": f"{shard_id}.json",
                "review_slice_template_sha256": _canonical_sha256(partial),
            }
        )
    stable_manifest = {
        "schema_version": REVIEW_MANIFEST_SCHEMA,
        "manifest_id": manifest_id,
        "contract_sha256": contract_sha256,
        "source_review_template_sha256": contract["source_review_template_sha256"],
        "review_id": review["review_id"],
        "author_agent_id": review["author_agent_id"],
        "global_targets_sha256": contract["global_targets_sha256"],
        "task_review_count": contract["task_review_count"],
        "max_reviews_per_shard": max_reviews_per_shard,
        "shard_count": total,
        "shards": manifest_shards,
    }
    manifest = {
        **stable_manifest,
        "manifest_sha256": _canonical_sha256(stable_manifest),
    }
    return manifest, slices


def shard_mapping_review(
    review_template_path: Path,
    output_dir: Path,
    *,
    max_reviews_per_shard: int,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Write bounded slices of a complete prepared mapping-review template."""

    review = _load_json(review_template_path)
    manifest, slices = _build_review_shards(
        review,
        max_reviews_per_shard=max_reviews_per_shard,
    )
    destination = output_dir.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    target_manifest = (
        manifest_path.expanduser().resolve()
        if manifest_path is not None
        else destination / "mapping_review_shards.json"
    )
    if target_manifest.parent != destination:
        raise MappingShardError(
            "Mapping review manifest must be written beside its shard files"
        )
    for manifest_shard, review_slice in zip(manifest["shards"], slices):
        _write_json(destination / manifest_shard["review_slice_file"], review_slice)
    _write_json(target_manifest, manifest)
    return manifest


def _validated_review_manifest(
    review: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    if manifest.get("schema_version") != REVIEW_MANIFEST_SCHEMA:
        raise MappingShardError("Unsupported mapping review shard manifest schema")
    raw_bound = manifest.get("max_reviews_per_shard")
    if not isinstance(raw_bound, int):
        raise MappingShardError("Review shard manifest has no integer shard bound")
    expected, _slices = _build_review_shards(
        review,
        max_reviews_per_shard=raw_bound,
    )
    if dict(manifest) != expected:
        raise MappingShardError(
            "Mapping review shard manifest is stale or differs from its template"
        )
    return expected


def _review_state(task_reviews: Sequence[Mapping[str, Any]]) -> str:
    verdicts = [str(item.get("verdict") or "") for item in task_reviews]
    if "unsupported" in verdicts:
        return "rejected"
    if "unable_to_determine" in verdicts:
        return "unable_to_determine"
    if "supported_with_caveat" in verdicts:
        return "approved_with_caveats"
    return "approved"


def merge_mapping_review(
    review_template_path: Path,
    manifest_path: Path,
    review_paths: Sequence[Path],
    output_path: Path,
    *,
    coordinator_agent_id: str,
    summary: str,
) -> dict[str, Any]:
    """Merge reviewed slices under a separate independent Codex coordinator."""

    coordinator = _require_safe_id(
        coordinator_agent_id,
        label="Mapping review coordinator agent_id",
    )
    normalized_summary = summary.strip()
    if not normalized_summary:
        raise MappingShardError("Mapping review coordinator summary is required")
    template = _load_json(review_template_path)
    template_records = _review_records(template)
    author_agent_id = str(template["author_agent_id"])
    mapping_author_ids = {
        str(agent_id)
        for item in template_records
        for agent_id in (
            item.get("targets", {}).get("mapping_author_agent_ids", [])
            if isinstance(item.get("targets"), dict)
            and isinstance(
                item.get("targets", {}).get("mapping_author_agent_ids"), list
            )
            else []
        )
    }
    if coordinator == author_agent_id or coordinator in mapping_author_ids:
        raise MappingShardError(
            "Mapping review coordinator must be independent from every mapping author"
        )
    manifest = _validated_review_manifest(
        template,
        _load_json(manifest_path),
    )
    expected_by_shard = {str(item["shard_id"]): item for item in manifest["shards"]}
    template_by_id = {str(item["task_id"]): item for item in template_records}
    contribution_by_shard: dict[str, dict[str, Any]] = {}
    review_by_task: dict[str, dict[str, Any]] = {}
    contributor_ids: set[str] = set()
    for review_path in review_paths:
        partial = _load_json(review_path)
        if partial.get("schema_version") != MAPPING_REVIEW_SCHEMA:
            raise MappingShardError("Unsupported partial mapping review schema")
        for key in ("review_id", "author_agent_id", "targets"):
            if partial.get(key) != template.get(key):
                raise MappingShardError(
                    f"Partial mapping review has stale global field: {key}"
                )
        raw_shard = partial.get("shard")
        if not isinstance(raw_shard, dict):
            raise MappingShardError("Partial mapping review has no shard pins")
        shard_id = str(raw_shard.get("shard_id") or "")
        manifest_shard = expected_by_shard.get(shard_id)
        if manifest_shard is None:
            raise MappingShardError(
                f"Partial mapping review references an unknown shard: {shard_id!r}"
            )
        if shard_id in contribution_by_shard:
            raise MappingShardError(f"Duplicate mapping review shard: {shard_id}")
        expected_pin = {
            "schema_version": REVIEW_SHARD_SCHEMA,
            "manifest_id": manifest["manifest_id"],
            "contract_sha256": manifest["contract_sha256"],
            "shard_id": shard_id,
            "index": manifest_shard["index"],
            "total": manifest["shard_count"],
            "source_review_template_sha256": manifest["source_review_template_sha256"],
            "task_ids": list(manifest_shard["task_ids"]),
            "task_review_template_sha256s": dict(
                manifest_shard["task_review_template_sha256s"]
            ),
        }
        if raw_shard != expected_pin:
            raise MappingShardError(
                f"Partial mapping review has stale shard pins: {shard_id}"
            )
        contributor = _codex_agent(
            partial.get("reviewer"),
            label=f"Mapping review contributor for {shard_id}",
        )
        contributor_id = str(contributor["agent_id"])
        if (
            contributor_id == author_agent_id
            or contributor.get("role") != "independent_mapping_reviewer"
            or contributor.get("independent_from_author") is not True
        ):
            raise MappingShardError(
                f"Mapping review contributor for {shard_id} is not independent"
            )
        contributor_ids.add(contributor_id)
        raw_reviews = partial.get("task_reviews")
        if not isinstance(raw_reviews, list):
            raise MappingShardError(
                f"Partial mapping review for {shard_id} requires task_reviews"
            )
        allowed_task_ids = set(manifest_shard["task_ids"])
        local_reviews: dict[str, dict[str, Any]] = {}
        for item in raw_reviews:
            if not isinstance(item, dict):
                raise MappingShardError("Each partial task review must be an object")
            task_id = str(item.get("task_id") or "")
            if task_id not in allowed_task_ids:
                raise MappingShardError(
                    f"Mapping review task {task_id!r} falls outside shard {shard_id}"
                )
            if task_id in local_reviews or task_id in review_by_task:
                raise MappingShardError(f"Duplicate mapping review task: {task_id!r}")
            template_item = template_by_id[task_id]
            if item.get("targets") != template_item.get("targets"):
                raise MappingShardError(
                    f"Mapping review task {task_id} has stale content targets"
                )
            task_author_ids = template_item["targets"].get(
                "mapping_author_agent_ids", []
            )
            if contributor_id in task_author_ids:
                raise MappingShardError(
                    f"Mapping review task {task_id} is assigned to an agent who "
                    "authored that mapping"
                )
            if item.get("verdict") not in ALLOWED_REVIEW_VERDICTS:
                raise MappingShardError(
                    f"Mapping review task {task_id} has an invalid verdict"
                )
            if not str(item.get("reason") or "").strip():
                raise MappingShardError(
                    f"Mapping review task {task_id} requires a reason"
                )
            reviewed_item = copy.deepcopy(item)
            reviewed_item["contributor_agent_id"] = contributor_id
            reviewed_item["review_shard_id"] = shard_id
            local_reviews[task_id] = reviewed_item
        if set(local_reviews) != allowed_task_ids:
            missing = sorted(allowed_task_ids - set(local_reviews))
            raise MappingShardError(
                f"Mapping review shard {shard_id} does not cover every task: "
                f"missing={missing}"
            )
        review_by_task.update(local_reviews)
        contribution_by_shard[shard_id] = {
            "shard_id": shard_id,
            "reviewer": contributor,
            "task_ids": list(manifest_shard["task_ids"]),
            "task_review_count": len(local_reviews),
            "summary": str(partial.get("summary") or "").strip(),
            "artifact_sha256": _canonical_sha256(partial),
        }

    if coordinator in contributor_ids:
        raise MappingShardError(
            "Mapping review coordinator must be separate from shard contributors"
        )
    missing_shards = sorted(set(expected_by_shard) - set(contribution_by_shard))
    if missing_shards:
        raise MappingShardError(
            f"Mapping review is missing required shards: {missing_shards}"
        )
    source_task_ids = [str(item["task_id"]) for item in template_records]
    contributions = [
        contribution_by_shard[str(item["shard_id"])] for item in manifest["shards"]
    ]
    ordered_reviews = [review_by_task[task_id] for task_id in source_task_ids]
    merged = copy.deepcopy(dict(template))
    merged["reviewer"] = {
        "execution": "codex_agent",
        "agent_id": coordinator,
        "role": "independent_mapping_reviewer",
        "tier": "coordinator",
        "independent_from_author": True,
    }
    merged["overall_verdict"] = _review_state(ordered_reviews)
    merged["summary"] = normalized_summary
    merged["task_reviews"] = ordered_reviews
    merged.pop("shard", None)
    merged["review_coordination"] = {
        "schema_version": REVIEW_COORDINATION_SCHEMA,
        "mode": "exact_shard_merge",
        "manifest_id": manifest["manifest_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "source_review_template_sha256": manifest["source_review_template_sha256"],
        "coordinator_agent_id": coordinator,
        "contribution_count": len(contributions),
        "contributions": contributions,
    }
    _write_json(output_path, merged)
    return merged


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    task_parser = subparsers.add_parser(
        "shard-tasks",
        help="Partition one complete mapping task artifact.",
    )
    task_parser.add_argument("tasks", type=Path)
    task_parser.add_argument("--output-dir", type=Path, required=True)
    task_parser.add_argument("--max-tasks-per-shard", type=int, required=True)
    task_parser.add_argument("--manifest", type=Path)

    decision_parser = subparsers.add_parser(
        "merge-decisions",
        help="Merge complete reviewed mapping-decision shards.",
    )
    decision_parser.add_argument("tasks", type=Path)
    decision_parser.add_argument("manifest", type=Path)
    decision_parser.add_argument("decision_shards", type=Path, nargs="*")
    decision_parser.add_argument("--coordinator-agent-id", required=True)
    decision_parser.add_argument("--output", type=Path, required=True)

    review_shard_parser = subparsers.add_parser(
        "shard-review",
        help="Partition one complete prepared mapping-review template.",
    )
    review_shard_parser.add_argument("review_template", type=Path)
    review_shard_parser.add_argument("--output-dir", type=Path, required=True)
    review_shard_parser.add_argument(
        "--max-reviews-per-shard",
        type=int,
        required=True,
    )
    review_shard_parser.add_argument("--manifest", type=Path)

    review_merge_parser = subparsers.add_parser(
        "merge-review",
        help="Merge complete review shards under an independent coordinator.",
    )
    review_merge_parser.add_argument("review_template", type=Path)
    review_merge_parser.add_argument("manifest", type=Path)
    review_merge_parser.add_argument("review_shards", type=Path, nargs="*")
    review_merge_parser.add_argument("--coordinator-agent-id", required=True)
    review_merge_parser.add_argument("--summary", required=True)
    review_merge_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected mechanical sharding operation."""

    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "shard-tasks":
            result = shard_mapping_tasks(
                args.tasks,
                args.output_dir,
                max_tasks_per_shard=args.max_tasks_per_shard,
                manifest_path=args.manifest,
            )
            LOGGER.info("Prepared %s mapping task shards", result["shard_count"])
        elif args.command == "merge-decisions":
            result = merge_mapping_decisions(
                args.tasks,
                args.manifest,
                args.decision_shards,
                args.output,
                coordinator_agent_id=args.coordinator_agent_id,
            )
            LOGGER.info("Merged %s mapping decisions", len(result["decisions"]))
        elif args.command == "shard-review":
            result = shard_mapping_review(
                args.review_template,
                args.output_dir,
                max_reviews_per_shard=args.max_reviews_per_shard,
                manifest_path=args.manifest,
            )
            LOGGER.info("Prepared %s mapping review shards", result["shard_count"])
        else:
            result = merge_mapping_review(
                args.review_template,
                args.manifest,
                args.review_shards,
                args.output,
                coordinator_agent_id=args.coordinator_agent_id,
                summary=args.summary,
            )
            LOGGER.info(
                "Merged %s mapping task reviews",
                len(result["task_reviews"]),
            )
    except MappingShardError as exc:
        LOGGER.error("Mapping shard operation failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
