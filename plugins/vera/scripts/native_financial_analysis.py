"""Inspect maintained Financial Analysis receipts and purpose-bound artifacts."""

from __future__ import annotations

import csv
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

__all__ = ["read_prepared"]
PAGE_SIZE = 30
MAX_PREVIEW_BYTES = 60_000


def json_page(value: Any, reference: str | None) -> dict[str, Any]:
    """Navigate exact JSON members; size bounds never choose semantic relevance."""
    selector = {"path": [], "offset": 0}
    if reference:
        if not reference.startswith("json:"):
            raise ValueError("Unknown prepared JSON selection")
        selector = json.loads(reference[5:])
    if not isinstance(selector, dict) or set(selector) != {"path", "offset"}:
        raise ValueError("Unknown prepared JSON selector fields")
    path, offset = selector["path"], selector["offset"]
    if (
        not isinstance(path, list)
        or len(path) > 20
        or not isinstance(offset, int)
        or isinstance(offset, bool)
        or offset < 0
    ):
        raise ValueError("Invalid prepared JSON selection")
    for key in path:
        if isinstance(value, dict) and isinstance(key, str) and key in value:
            value = value[key]
        elif (
            isinstance(value, list)
            and isinstance(key, int)
            and not isinstance(key, bool)
            and 0 <= key < len(value)
        ):
            value = value[key]
        else:
            raise ValueError("Unknown member in prepared JSON artifact")
    if not isinstance(value, (dict, list)):
        if offset:
            raise ValueError("Scalar prepared value has no page offset")
        return {"kind": "value", "path": path, "value": value}
    members = list(value.items()) if isinstance(value, dict) else list(enumerate(value))
    if offset and offset >= len(members):
        raise ValueError("Prepared JSON page is outside the artifact")
    entries = []
    for key, member in members[offset : offset + PAGE_SIZE]:
        child = "json:" + json.dumps(
            {"path": [*path, key], "offset": 0},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        complete = len(json.dumps(member, ensure_ascii=False).encode()) <= 1200
        entries.append(
            {
                "name": str(key),
                "source_ref": child,
                "value": member if complete else None,
                "display": "complete_value" if complete else "child_reference_only",
                "member_count": (
                    len(member) if isinstance(member, (dict, list)) else None
                ),
            }
        )
    return {
        "kind": "object" if isinstance(value, dict) else "array",
        "path": path,
        "entries": entries,
        "offset": offset,
        "total": len(members),
        "has_more": offset + PAGE_SIZE < len(members),
        "coverage": "This exact member page only. Child references require a separate explicit selection.",
    }


def read_prepared(
    root: Path,
    loaded: dict[str, Any],
    args: dict[str, Any],
    read_json: Callable[[Path], dict[str, Any]],
    *,
    exact_case_path: Path | None = None,
) -> dict[str, Any]:
    """Read exact producer records; checksum consistency is not professional approval."""
    sys.path.insert(0, str(root / "scripts"))
    engine = importlib.import_module("run_pack")
    model_use = importlib.import_module("model_use")
    kernel = importlib.import_module("preparation_contract_kernel")
    from vera_assurance import (
        load_client_engagement_context_file,
        validate_client_workflow_run,
    )

    output = Path(loaded["output_dir"])
    candidates = [
        p for p in (output, output / "prepared") if (p / engine.RECEIPT_NAME).exists()
    ]
    if len(candidates) != 1:
        raise ValueError("Financial Analysis needs one exact prepared pack location")
    directory = candidates[0]
    receipt = read_json(directory / engine.RECEIPT_NAME)
    manifest = model_use.validate_manifest(
        read_json(directory / model_use.MANIFEST_NAME)
    )
    pack_id = receipt["pack_id"]
    if pack_id not in engine.PACKS or manifest["pack_id"] != pack_id:
        raise ValueError("Financial Analysis pack identity does not match")
    content = {key: value for key, value in receipt.items() if key != "content_sha256"}
    if kernel.canonical_json_sha256(content) != receipt["content_sha256"]:
        raise ValueError("Financial Analysis execution receipt is stale")
    spec = engine.PACKS[pack_id]
    # Reuse the producer's exact implementation receipt format, not a new rule set.
    implementations = engine._implementation_snapshots(spec.implementation_files)
    if (
        receipt["schema_version"] != "vera.financial_analysis_pack_execution.v3"
        or receipt["implementation_files"] != implementations
        or receipt["implementation_set_sha256"]
        != kernel.canonical_json_sha256(implementations)
        or receipt["recipe_id"] != spec.recipe_id
        or receipt["engine_version"] != spec.engine_version
        or receipt["engine_sha256"] != implementations[0]["sha256"]
        or receipt["report_ready"] is not False
    ):
        raise ValueError("Financial Analysis recipe or review boundary changed")
    population = manifest["source_population"]
    if population["case_sha256"] != receipt["case_sha256"]:
        raise ValueError("Financial Analysis case receipt does not match")
    # Fixed maintained case locations plus exact receipted inputs; no UI path.
    if exact_case_path is not None:
        if exact_case_path != output / "case" / "case.json":
            raise ValueError(
                "Native Financial Analysis case is outside its exact version"
            )
        possible = [exact_case_path]
    else:
        possible = [output / "case.json", output / "case" / "case.json"]
        possible.extend(
            Path(row["path"])
            for row in loaded["context"]["input_bindings"]
            if Path(row["path"]).suffix == ".json"
        )
    cases = []
    for path in dict.fromkeys(possible):
        if (
            path.is_file()
            and kernel.file_snapshot_beneath(path, root=path.parent)[1]
            == receipt["case_sha256"]
        ):
            cases.append(path)
    if len(cases) != 1:
        raise ValueError("Financial Analysis needs one exact current case")
    case_path = cases[0]
    source_bindings = dict(engine.declared_case_input_bindings(case_path, pack_id))
    sealed_sources = {row["artifact_id"]: row for row in population["source_artifacts"]}
    if len(sealed_sources) != len(population["source_artifacts"]) or set(
        sealed_sources
    ) != set(source_bindings):
        raise ValueError("Financial Analysis source population does not match")
    for identity, path in source_bindings.items():
        count, sha = kernel.file_snapshot_beneath(path, root=case_path.parent)
        if (count, sha) != (
            sealed_sources[identity]["byte_count"],
            sealed_sources[identity]["sha256"],
        ):
            raise ValueError(
                "Financial Analysis source no longer matches the sealed manifest"
            )
    context = load_client_engagement_context_file(
        Path(loaded["context_path"]),
        expected_workflow_id="financial-analysis",
        input_paths=[case_path],
        output_dir=directory,
        allowed_statuses=("running", "ready_for_review", "completed"),
    )
    validate_client_workflow_run(
        context,
        expected_workflow_id="financial-analysis",
        input_paths=[case_path, *source_bindings.values()],
        output_dir=directory,
    )
    artifacts = receipt["output_artifacts"]
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 200:
        raise ValueError(
            "Financial Analysis output population exceeds its panel bounds"
        )
    if kernel.canonical_json_sha256(artifacts) != receipt["output_set_sha256"]:
        raise ValueError("Financial Analysis output set receipt is stale")
    if len({row["path"] for row in artifacts}) != len(artifacts) or len(
        {row["artifact_ref"] for row in artifacts}
    ) != len(artifacts):
        raise ValueError("Financial Analysis has ambiguous artifacts")
    for row in artifacts:
        path = Path(row["path"])
        if (
            path.is_absolute()
            or len(path.parts) != 1
            or path.name in {".", "..", engine.RECEIPT_NAME}
        ):
            raise ValueError("Financial Analysis output is outside its prepared pack")
        count, sha = kernel.file_snapshot_beneath(directory / path, root=directory)
        if (count, sha) != (row["byte_count"], row["sha256"]):
            raise ValueError("Financial Analysis prepared output changed")
    defaults = manifest["default_model_use"]["artifacts"]
    expected = [row for row in artifacts if row["path"] != model_use.MANIFEST_NAME]
    expected_by_id = {row["artifact_ref"]: row for row in expected}
    if len(defaults) != len(expected) or {
        row["artifact_id"] for row in defaults
    } != set(expected_by_id):
        raise ValueError("Financial Analysis model-use population does not match")
    for row in defaults:
        saved = expected_by_id[row["artifact_id"]]
        if any(row[key] != saved[key] for key in ("path", "byte_count", "sha256")):
            raise ValueError("Financial Analysis model-use artifact does not match")
    if (
        manifest["default_model_use"]["raw_source_files_included"] is not False
        or manifest["status"] != receipt["status"]
    ):
        raise ValueError("Financial Analysis prepared-first boundary changed")
    selected = None
    selected_id = args.get("item_id")
    if selected_id:
        row = next((row for row in defaults if row["artifact_id"] == selected_id), None)
        if row is None:
            raise ValueError("Unknown prepared Financial Analysis artifact")
        path = directory / row["path"]
        if path.suffix == ".csv":
            reference = args.get("source_ref", "rows-0")
            match = re.fullmatch(r"rows-(0|[1-9][0-9]*)", reference)
            if match is None:
                raise ValueError("Unknown prepared table page")
            offset = int(match[1])
            rows = []
            total = 0
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for total, item in enumerate(reader, 1):
                    if offset <= total - 1 < offset + PAGE_SIZE:
                        rows.append(item)
            prepared = {
                "columns": reader.fieldnames,
                "rows": rows,
                "offset": offset,
                "total": total,
                "has_more": offset + PAGE_SIZE < total,
            }
            if offset and offset >= total:
                raise ValueError("Prepared table page is outside the artifact")
        elif path.suffix == ".json":
            prepared = json_page(read_json(path), args.get("source_ref"))
        else:
            raise ValueError("Prepared artifact format requires the specialist route")
        selected = {
            "id": selected_id,
            "title": row["path"],
            "purpose": row["purpose"],
            "prepared_context": prepared,
            "source_scope": "one producer-declared prepared artifact; raw source files excluded",
        }
        if len(json.dumps(selected, ensure_ascii=False).encode()) > MAX_PREVIEW_BYTES:
            raise ValueError("Prepared artifact page exceeds selected context bounds")
        if kernel.file_snapshot_beneath(path, root=directory) != (
            row["byte_count"],
            row["sha256"],
        ):
            raise ValueError("Prepared artifact changed during reading")
    revision = kernel.canonical_json_sha256({"receipt": receipt, "manifest": manifest})
    if (
        read_json(directory / engine.RECEIPT_NAME) != receipt
        or read_json(directory / model_use.MANIFEST_NAME) != manifest
    ):
        raise ValueError("Financial Analysis receipt changed during reading")
    offset = args.get("offset", 0)
    items = [
        {
            "id": row["artifact_id"],
            "title": row["path"],
            "purpose": row["purpose"],
            "status": receipt["status"],
        }
        for row in defaults
    ]
    return {
        "revision": revision,
        "items": items[offset : offset + PAGE_SIZE],
        "total": len(items),
        "selection": selected,
        "data": {
            "selection": {"source_ref": args.get("source_ref")},
            "pack_id": pack_id,
            "recipe_id": receipt["recipe_id"],
            "status": receipt["status"],
            "report_ready": False,
            "local_review_read_only": True,
            "source_access": "prepared_artifacts_first; named raw-source requests remain in the maintained specialist route",
            "verification": "current checksums/recipe/input bindings only; no professional approval or independent recalculation inferred",
        },
    }
