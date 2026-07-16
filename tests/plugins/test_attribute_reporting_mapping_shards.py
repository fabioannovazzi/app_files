from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "attribute-reporting" / "scripts"
SHARDS_PATH = SCRIPTS / "mapping_shards.py"
REPORTING_PATH = SCRIPTS / "attribute_reporting.py"
TAXONOMY_SHA256 = "a" * 64


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_previous_reporting = sys.modules.get("attribute_reporting")
reporting = _load_module("attribute_reporting", REPORTING_PATH)
shards = _load_module("attribute_reporting_mapping_shards_test", SHARDS_PATH)
if _previous_reporting is None:
    sys.modules.pop("attribute_reporting", None)
else:
    sys.modules["attribute_reporting"] = _previous_reporting


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _task_id(product_id: str) -> str:
    stable_key = f"retailer|cashmere|parent|{product_id}||material"
    return "map-" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:24]


def _mapping_tasks(task_count: int = 5) -> dict[str, Any]:
    records = []
    for index in range(task_count):
        product_id = f"product-{index + 1}"
        records.append(
            {
                "task_id": _task_id(product_id),
                "product": {
                    "retailer": "retailer",
                    "row_type": "parent",
                    "parent_product_id": product_id,
                    "variant_id": "",
                    "category_key": "cashmere",
                    "source_row_sha256": hashlib.sha256(
                        product_id.encode("utf-8")
                    ).hexdigest(),
                    "brand": "Example",
                    "title": f"Cashmere sweater {index + 1}",
                    "description": "100% cashmere crew neck sweater.",
                    "pdp_url": f"https://retailer.example/{product_id}",
                    "local_images": [],
                },
                "attribute": {
                    "id": "material",
                    "label": "Material",
                    "selection": "single",
                    "allowed_values": [
                        {"id": "cashmere", "label": "Cashmere"},
                        {"id": "blend", "label": "Cashmere blend"},
                    ],
                },
                "existing_evidence": {},
                "mapping_reason": "unresolved",
            }
        )
    return {
        "schema_version": "attribute_reporting.mapping_tasks.v1",
        "generated_at": "2026-07-16T08:00:00+00:00",
        "taxonomy_snapshot": {
            "version": "2026-07-16",
            "sha256": TAXONOMY_SHA256,
            "category_key": "cashmere",
        },
        "scope": {
            "retailer": "retailer",
            "category_key": "cashmere",
            "row_type": "parent",
            "source_package": "/private/run/package",
            "source_package_sha256": "b" * 64,
            "source_pack_manifest_sha256": "c" * 64,
            "source_matrix_sha256": "d" * 64,
            "summary_sha256": "e" * 64,
            "package_integrity_sha256": "f" * 64,
        },
        "coverage": {
            "product_rows": task_count,
            "resolved_attribute_cells": 0,
            "unresolved_attribute_cells": task_count,
            "migration_recheck_tasks": 0,
            "variant_attribute_cells_skipped": 0,
            "task_count_before_limit": task_count,
            "task_count": task_count,
            "truncated": False,
            "include_resolved": False,
        },
        "tasks": records,
    }


def _prepare_task_shards(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any], list[Path]]:
    tasks = _mapping_tasks()
    tasks_path = tmp_path / "mapping_tasks.json"
    output_dir = tmp_path / "task_shards"
    _write_json(tasks_path, tasks)
    manifest = shards.shard_mapping_tasks(
        tasks_path,
        output_dir,
        max_tasks_per_shard=2,
    )
    manifest_path = output_dir / "mapping_task_shards.json"
    decision_paths: list[Path] = []
    for index, item in enumerate(manifest["shards"], start=1):
        path = output_dir / item["decision_template_file"]
        partial = _read_json(path)
        partial["agent"] = {
            "execution": "codex_agent",
            "agent_id": f"mapping-contributor-{index}",
            "tier": "low_cost",
        }
        partial["decisions"] = [
            {
                "task_id": task_id,
                "status": "mapped",
                "value_id": "cashmere",
                "value_label": "Cashmere",
                "confidence": "high",
                "reason": "The product description explicitly states 100% cashmere.",
            }
            for task_id in partial["shard"]["task_ids"]
        ]
        _write_json(path, partial)
        decision_paths.append(path)
    return tasks_path, manifest_path, manifest, decision_paths


def test_shard_mapping_tasks_is_bounded_deterministic_and_exact(
    tmp_path: Path,
) -> None:
    tasks = _mapping_tasks()
    tasks_path = tmp_path / "mapping_tasks.json"
    _write_json(tasks_path, tasks)

    first = shards.shard_mapping_tasks(
        tasks_path,
        tmp_path / "first",
        max_tasks_per_shard=2,
    )
    second = shards.shard_mapping_tasks(
        tasks_path,
        tmp_path / "second",
        max_tasks_per_shard=2,
    )

    assert first == second
    assert first["shard_count"] == 3
    assert first["task_count"] == 5
    assert first["source_tasks_sha256"] == _canonical_sha256(tasks)
    assert first["manifest_sha256"] == _canonical_sha256(
        {key: value for key, value in first.items() if key != "manifest_sha256"}
    )
    observed_task_ids: list[str] = []
    for item in first["shards"]:
        task_slice = _read_json(tmp_path / "first" / item["task_slice_file"])
        assert 0 < len(task_slice["tasks"]) <= 2
        assert item["task_slice_sha256"] == _canonical_sha256(task_slice)
        assert task_slice["shard"]["task_sha256s"] == {
            task["task_id"]: _canonical_sha256(task) for task in task_slice["tasks"]
        }
        observed_task_ids.extend(item["task_ids"])
    assert observed_task_ids == [task["task_id"] for task in tasks["tasks"]]


def test_merge_mapping_decisions_preserves_order_and_contributor_provenance(
    tmp_path: Path,
) -> None:
    tasks_path, manifest_path, manifest, decision_paths = _prepare_task_shards(tmp_path)
    output_path = tmp_path / "mapping_decisions.json"

    merged = shards.merge_mapping_decisions(
        tasks_path,
        manifest_path,
        list(reversed(decision_paths)),
        output_path,
        coordinator_agent_id="mapping-coordinator",
    )

    tasks = _read_json(tasks_path)
    assert [item["task_id"] for item in merged["decisions"]] == [
        item["task_id"] for item in tasks["tasks"]
    ]
    assert merged["agent"] == {
        "execution": "codex_agent",
        "agent_id": "mapping-coordinator",
        "role": "mapping_shard_coordinator",
    }
    coordination = merged["coordination"]
    assert coordination["manifest_sha256"] == manifest["manifest_sha256"]
    assert coordination["contribution_count"] == 3
    assert [item["shard_id"] for item in coordination["contributions"]] == [
        item["shard_id"] for item in manifest["shards"]
    ]
    assert all(
        item["agent"]["agent_id"].startswith("mapping-contributor-")
        and len(item["artifact_sha256"]) == 64
        for item in coordination["contributions"]
    )
    assert all(
        item["contributor_agent_id"].startswith("mapping-contributor-")
        and item["mapping_shard_id"].startswith("mapping-task-shard-")
        for item in merged["decisions"]
    )
    validated = reporting.validate_mapping_payloads(tasks, merged)
    assert validated["status"] == "valid"
    assert validated["mapping_count"] == 5
    assert _read_json(output_path) == merged


def test_merge_mapping_decisions_rejects_missing_shard(tmp_path: Path) -> None:
    tasks_path, manifest_path, _manifest, decision_paths = _prepare_task_shards(
        tmp_path
    )

    with pytest.raises(shards.MappingShardError, match="missing required shards"):
        shards.merge_mapping_decisions(
            tasks_path,
            manifest_path,
            decision_paths[:-1],
            tmp_path / "merged.json",
            coordinator_agent_id="mapping-coordinator",
        )


def test_merge_mapping_decisions_rejects_duplicate_shard(tmp_path: Path) -> None:
    tasks_path, manifest_path, _manifest, decision_paths = _prepare_task_shards(
        tmp_path
    )

    with pytest.raises(shards.MappingShardError, match="Duplicate mapping decision"):
        shards.merge_mapping_decisions(
            tasks_path,
            manifest_path,
            [decision_paths[0], *decision_paths],
            tmp_path / "merged.json",
            coordinator_agent_id="mapping-coordinator",
        )


def test_merge_mapping_decisions_rejects_stale_shard_pins(tmp_path: Path) -> None:
    tasks_path, manifest_path, _manifest, decision_paths = _prepare_task_shards(
        tmp_path
    )
    stale = _read_json(decision_paths[0])
    stale["shard"]["source_tasks_sha256"] = "0" * 64
    _write_json(decision_paths[0], stale)

    with pytest.raises(shards.MappingShardError, match="stale shard pins"):
        shards.merge_mapping_decisions(
            tasks_path,
            manifest_path,
            decision_paths,
            tmp_path / "merged.json",
            coordinator_agent_id="mapping-coordinator",
        )


def test_merge_mapping_decisions_rejects_out_of_slice_task(tmp_path: Path) -> None:
    tasks_path, manifest_path, manifest, decision_paths = _prepare_task_shards(tmp_path)
    out_of_slice = _read_json(decision_paths[0])
    out_of_slice["decisions"][0]["task_id"] = manifest["shards"][1]["task_ids"][0]
    _write_json(decision_paths[0], out_of_slice)

    with pytest.raises(shards.MappingShardError, match="falls outside shard"):
        shards.merge_mapping_decisions(
            tasks_path,
            manifest_path,
            decision_paths,
            tmp_path / "merged.json",
            coordinator_agent_id="mapping-coordinator",
        )


def test_merge_mapping_decisions_rejects_incomplete_slice(tmp_path: Path) -> None:
    tasks_path, manifest_path, _manifest, decision_paths = _prepare_task_shards(
        tmp_path
    )
    incomplete = _read_json(decision_paths[0])
    incomplete["decisions"].pop()
    _write_json(decision_paths[0], incomplete)

    with pytest.raises(shards.MappingShardError, match="does not cover every task"):
        shards.merge_mapping_decisions(
            tasks_path,
            manifest_path,
            decision_paths,
            tmp_path / "merged.json",
            coordinator_agent_id="mapping-coordinator",
        )


def _prepare_review_shards(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[Path],
]:
    tasks_path, task_manifest_path, _task_manifest, decision_paths = (
        _prepare_task_shards(tmp_path)
    )
    decisions_path = tmp_path / "mapping_decisions.json"
    decisions = shards.merge_mapping_decisions(
        tasks_path,
        task_manifest_path,
        decision_paths,
        decisions_path,
        coordinator_agent_id="mapping-coordinator",
    )
    validated_path = tmp_path / "validated_mappings.json"
    validated = reporting.validate_mapping_decisions(
        tasks_path,
        decisions_path,
        validated_path,
    )
    review_template_path = tmp_path / "mapping_review_template.json"
    reporting.create_mapping_review_template(
        tasks_path,
        decisions_path,
        validated_path,
        review_template_path,
        reviewer_agent_id="review-template-owner",
    )
    review_dir = tmp_path / "review_shards"
    review_manifest = shards.shard_mapping_review(
        review_template_path,
        review_dir,
        max_reviews_per_shard=2,
    )
    review_paths: list[Path] = []
    for index, item in enumerate(review_manifest["shards"], start=1):
        path = review_dir / item["review_slice_file"]
        partial = _read_json(path)
        partial["reviewer"] = {
            "execution": "codex_agent",
            "agent_id": f"review-contributor-{index}",
            "role": "independent_mapping_reviewer",
            "tier": "low_cost",
            "independent_from_author": True,
        }
        partial["summary"] = "Every assigned mapping was independently reviewed."
        for item_review in partial["task_reviews"]:
            item_review["verdict"] = "supported"
            item_review["reason"] = (
                "The selected value is directly supported by the product evidence."
            )
        _write_json(path, partial)
        review_paths.append(path)
    return (
        review_template_path,
        review_dir / "mapping_review_shards.json",
        _read_json(tasks_path),
        decisions,
        validated,
        review_paths,
    )


def test_review_shards_merge_under_separate_independent_coordinator(
    tmp_path: Path,
) -> None:
    (
        template_path,
        manifest_path,
        tasks,
        decisions,
        validated,
        review_paths,
    ) = _prepare_review_shards(tmp_path)

    merged = shards.merge_mapping_review(
        template_path,
        manifest_path,
        list(reversed(review_paths)),
        tmp_path / "mapping_review.json",
        coordinator_agent_id="review-coordinator",
        summary="All five mappings were independently reviewed and supported.",
    )

    assert merged["overall_verdict"] == "approved"
    assert merged["reviewer"]["agent_id"] == "review-coordinator"
    assert merged["reviewer"]["independent_from_author"] is True
    assert merged["review_coordination"]["contribution_count"] == 3
    assert all(
        item["contributor_agent_id"].startswith("review-contributor-")
        and item["review_shard_id"].startswith("mapping-review-shard-")
        for item in merged["task_reviews"]
    )
    validation = reporting.validate_mapping_review_payloads(
        tasks,
        decisions,
        validated,
        merged,
    )
    assert validation["status"] == "valid"
    assert validation["review_state"] == "approved"
    assert validation["task_count"] == 5


def test_merge_mapping_review_rejects_nonseparate_coordinator(
    tmp_path: Path,
) -> None:
    (
        template_path,
        manifest_path,
        _tasks,
        _decisions,
        _validated,
        review_paths,
    ) = _prepare_review_shards(tmp_path)

    with pytest.raises(shards.MappingShardError, match="separate from shard"):
        shards.merge_mapping_review(
            template_path,
            manifest_path,
            review_paths,
            tmp_path / "mapping_review.json",
            coordinator_agent_id="review-contributor-1",
            summary="Coordinator review complete.",
        )


def test_merge_mapping_review_rejects_mapping_contributor_reviewing_own_tasks(
    tmp_path: Path,
) -> None:
    (
        template_path,
        manifest_path,
        _tasks,
        _decisions,
        _validated,
        review_paths,
    ) = _prepare_review_shards(tmp_path)
    conflicted = _read_json(review_paths[0])
    conflicted["reviewer"]["agent_id"] = "mapping-contributor-1"
    _write_json(review_paths[0], conflicted)

    with pytest.raises(shards.MappingShardError, match="authored that mapping"):
        shards.merge_mapping_review(
            template_path,
            manifest_path,
            review_paths,
            tmp_path / "mapping_review.json",
            coordinator_agent_id="review-coordinator",
            summary="Coordinator review complete.",
        )


def test_mapping_review_validator_rejects_per_task_author_as_reviewer(
    tmp_path: Path,
) -> None:
    (
        template_path,
        manifest_path,
        tasks,
        decisions,
        validated,
        review_paths,
    ) = _prepare_review_shards(tmp_path)
    merged = shards.merge_mapping_review(
        template_path,
        manifest_path,
        review_paths,
        tmp_path / "mapping_review.json",
        coordinator_agent_id="review-coordinator",
        summary="All mappings were independently reviewed.",
    )
    first_task_id = str(merged["task_reviews"][0]["task_id"])
    first_decision = next(
        item for item in decisions["decisions"] if item["task_id"] == first_task_id
    )
    merged["task_reviews"][0]["contributor_agent_id"] = first_decision[
        "contributor_agent_id"
    ]

    with pytest.raises(reporting.ContractError, match="not independent"):
        reporting.validate_mapping_review_payloads(
            tasks,
            decisions,
            validated,
            merged,
        )
