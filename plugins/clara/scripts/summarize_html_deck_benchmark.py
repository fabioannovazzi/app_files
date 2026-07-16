#!/usr/bin/env python3
"""Validate and summarize controlled Clara HTML-versus-PPTX benchmark records."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = ["summarize_benchmark", "validate_suite"]

LOGGER = logging.getLogger(__name__)
RUN_SCHEMA = "clara.html_deck_benchmark_runs.v1"
SUITE_SCHEMA = "clara.html_deck_benchmark_suite.v1"
SUMMARY_SCHEMA = "clara.html_deck_benchmark_summary.v1"
SHA256_LENGTH = 64


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a list")
    return list(value)


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value.strip()


def _sha256(value: Any, *, label: str) -> str:
    digest = _text(value, label=label).lower()
    if len(digest) != SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return digest


def _positive_int(value: Any, *, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: Any, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _timestamp(value: Any, *, label: str) -> datetime:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_sha256(files: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for item in sorted(files, key=lambda entry: str(entry["path"])):
        rows.append(f"{item['path']}\0{item['sha256']}\n")
    return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest()


def _run_index(
    runs: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for position, run in enumerate(runs, start=1):
        case_id = _text(run.get("case_id"), label=f"{label}[{position}].case_id")
        output_format = _text(
            run.get("format"), label=f"{label}[{position}].format"
        ).upper()
        key = (case_id, output_format)
        if key in result:
            raise ValueError(f"duplicate benchmark run in {label}: {key}")
        result[key] = run
    return result


def validate_suite(suite: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the benchmark contract and return normalized indexes."""

    if suite.get("schema_version") != SUITE_SCHEMA:
        raise ValueError("unsupported benchmark suite schema")
    _text(suite.get("suite_id"), label="suite.suite_id")
    raw_skill_identity = _mapping(
        suite.get("candidate_skill_identity"), label="suite.candidate_skill_identity"
    )
    if set(raw_skill_identity) != {"clara", "presentations"}:
        raise ValueError("candidate skill identity must bind Clara and Presentations")
    candidate_skill_identity: dict[str, dict[str, str]] = {}
    for skill_name in ("clara", "presentations"):
        raw_identity = _mapping(
            raw_skill_identity[skill_name], label=f"identity {skill_name}"
        )
        candidate_skill_identity[skill_name] = {
            "version": _text(
                raw_identity.get("version"), label=f"identity {skill_name}.version"
            ),
            "skill_sha256": _sha256(
                raw_identity.get("skill_sha256"),
                label=f"identity {skill_name}.skill_sha256",
            ),
        }
        if skill_name == "clara":
            candidate_skill_identity[skill_name]["plugin_manifest_sha256"] = _sha256(
                raw_identity.get("plugin_manifest_sha256"),
                label="identity clara.plugin_manifest_sha256",
            )
            candidate_skill_identity[skill_name]["runtime_tree_sha256"] = _sha256(
                raw_identity.get("runtime_tree_sha256"),
                label="identity clara.runtime_tree_sha256",
            )
        else:
            candidate_skill_identity[skill_name]["skill_tree_sha256"] = _sha256(
                raw_identity.get("skill_tree_sha256"),
                label="identity presentations.skill_tree_sha256",
            )
    limitations = _mapping(
        suite.get("baseline_limitations"), label="suite.baseline_limitations"
    )
    if limitations.get("raw_prior_jsonl_available") is not False:
        raise ValueError("suite must disclose unavailable raw historical JSONL")
    controls = _mapping(suite.get("controls"), label="suite.controls")
    if not controls or any(value is not True for value in controls.values()):
        raise ValueError("every declared suite control must be true")

    mechanical_gates = tuple(
        _text(item, label="suite.mechanical_gates[]")
        for item in _sequence(
            suite.get("mechanical_gates"), label="suite.mechanical_gates"
        )
    )
    if not mechanical_gates or len(mechanical_gates) != len(set(mechanical_gates)):
        raise ValueError("suite.mechanical_gates must be non-empty and unique")
    gate_set = set(mechanical_gates)

    judgement = _mapping(
        suite.get("semantic_judgement"), label="suite.semantic_judgement"
    )
    dimensions = tuple(
        _text(item, label="suite.semantic_judgement.dimensions[]")
        for item in _sequence(
            judgement.get("dimensions"),
            label="suite.semantic_judgement.dimensions",
        )
    )
    if not dimensions or len(dimensions) != len(set(dimensions)):
        raise ValueError("semantic dimensions must be non-empty and unique")
    reviewer_types = tuple(
        _text(item, label="suite.semantic_judgement.required_reviewer_types[]")
        for item in _sequence(
            judgement.get("required_reviewer_types"),
            label="suite.semantic_judgement.required_reviewer_types",
        )
    )
    allowed_reviewer_types = {"human", "model"}
    if (
        not reviewer_types
        or len(reviewer_types) != len(set(reviewer_types))
        or not set(reviewer_types).issubset(allowed_reviewer_types)
    ):
        raise ValueError(
            "semantic required reviewer types must be unique human/model values"
        )
    optional_reviewer_types = tuple(
        _text(item, label="suite.semantic_judgement.optional_reviewer_types[]")
        for item in _sequence(
            judgement.get("optional_reviewer_types", []),
            label="suite.semantic_judgement.optional_reviewer_types",
        )
    )
    if (
        len(optional_reviewer_types) != len(set(optional_reviewer_types))
        or not set(optional_reviewer_types).issubset(allowed_reviewer_types)
        or set(optional_reviewer_types).intersection(reviewer_types)
    ):
        raise ValueError(
            "semantic optional reviewer types must be disjoint human/model values"
        )
    score_min = _finite_number(
        judgement.get("score_min"), label="suite.semantic_judgement.score_min"
    )
    score_max = _finite_number(
        judgement.get("score_max"), label="suite.semantic_judgement.score_max"
    )
    if score_min >= score_max:
        raise ValueError("semantic score_min must be below score_max")

    cases = [
        _mapping(item, label="suite.cases[]")
        for item in _sequence(suite.get("cases"), label="suite.cases")
    ]
    if not cases:
        raise ValueError("suite.cases must not be empty")
    case_by_id: dict[str, Mapping[str, Any]] = {}
    required_checks: dict[tuple[str, str], tuple[str, ...]] = {}
    source_manifest_by_case: dict[str, str] = {}
    baseline_manifest_by_case: dict[str, str] = {}
    expected_matrix: set[tuple[str, str]] = set()
    for case in cases:
        case_id = _text(case.get("id"), label="suite.cases[].id")
        if case_id in case_by_id:
            raise ValueError(f"duplicate benchmark case: {case_id}")
        mode = _text(case.get("mode"), label=f"case {case_id}.mode")
        if mode not in {"create", "revise"}:
            raise ValueError(f"case {case_id}.mode must be create or revise")
        case_by_id[case_id] = case
        _text(
            case.get("fixture_subdirectory"),
            label=f"case {case_id}.fixture_subdirectory",
        )
        _text(case.get("instruction_file"), label=f"case {case_id}.instruction_file")
        _text(case.get("spec_file"), label=f"case {case_id}.spec_file")

        manifest = _mapping(
            case.get("source_manifest"), label=f"case {case_id}.source_manifest"
        )
        if manifest.get("algorithm") != "sha256":
            raise ValueError(f"case {case_id} source manifest must use sha256")
        manifest_files = [
            _mapping(item, label=f"case {case_id}.source_manifest.files[]")
            for item in _sequence(
                manifest.get("files"),
                label=f"case {case_id}.source_manifest.files",
            )
        ]
        if not manifest_files:
            raise ValueError(f"case {case_id} source manifest must not be empty")
        paths: set[str] = set()
        normalized_files: list[Mapping[str, Any]] = []
        for item in manifest_files:
            path = _text(item.get("path"), label=f"case {case_id} manifest path")
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError(f"case {case_id} manifest paths must be relative")
            if path in paths:
                raise ValueError(f"case {case_id} has duplicate manifest path: {path}")
            paths.add(path)
            normalized_files.append(
                {
                    "path": path,
                    "sha256": _sha256(
                        item.get("sha256"), label=f"case {case_id} manifest {path}"
                    ),
                }
            )
        declared_manifest_hash = _sha256(
            manifest.get("manifest_sha256"),
            label=f"case {case_id}.source_manifest.manifest_sha256",
        )
        calculated_manifest_hash = _manifest_sha256(normalized_files)
        if declared_manifest_hash != calculated_manifest_hash:
            raise ValueError(f"case {case_id} source manifest fingerprint is invalid")
        source_manifest_by_case[case_id] = declared_manifest_hash
        baseline_evidence = _mapping(
            case.get("baseline_evidence"), label=f"case {case_id}.baseline_evidence"
        )
        if baseline_evidence.get("algorithm") != "sha256":
            raise ValueError(f"case {case_id} baseline evidence must use sha256")
        baseline_files = [
            _mapping(item, label=f"case {case_id}.baseline_evidence.files[]")
            for item in _sequence(
                baseline_evidence.get("files"),
                label=f"case {case_id}.baseline_evidence.files",
            )
        ]
        normalized_baseline_files = [
            {
                "path": _text(
                    item.get("path"), label=f"case {case_id} baseline evidence path"
                ),
                "sha256": _sha256(
                    item.get("sha256"), label=f"case {case_id} baseline evidence hash"
                ),
            }
            for item in baseline_files
        ]
        baseline_manifest_hash = _sha256(
            baseline_evidence.get("manifest_sha256"),
            label=f"case {case_id}.baseline_evidence.manifest_sha256",
        )
        if baseline_manifest_hash != _manifest_sha256(normalized_baseline_files):
            raise ValueError(f"case {case_id} baseline evidence fingerprint is invalid")
        baseline_manifest_by_case[case_id] = baseline_manifest_hash

        formats = tuple(
            _text(item, label=f"case {case_id}.required_formats[]").upper()
            for item in _sequence(
                case.get("required_formats"),
                label=f"case {case_id}.required_formats",
            )
        )
        if set(formats) != {"HTML", "PPTX"} or len(formats) != 2:
            raise ValueError(f"case {case_id} must require HTML and PPTX exactly once")
        by_format = _mapping(
            case.get("required_checks_by_format"),
            label=f"case {case_id}.required_checks_by_format",
        )
        if {str(key).upper() for key in by_format} != set(formats):
            raise ValueError(
                f"case {case_id} check formats must match required_formats"
            )
        for output_format in formats:
            checks = tuple(
                _text(item, label=f"case {case_id}.{output_format}.checks[]")
                for item in _sequence(
                    by_format.get(output_format),
                    label=f"case {case_id}.{output_format}.checks",
                )
            )
            if not checks or len(checks) != len(set(checks)):
                raise ValueError(
                    f"case {case_id}.{output_format} checks must be non-empty and unique"
                )
            unknown_gates = sorted(set(checks) - gate_set)
            if unknown_gates:
                raise ValueError(
                    f"case {case_id}.{output_format} uses undeclared gates: {unknown_gates}"
                )
            key = (case_id, output_format)
            required_checks[key] = checks
            expected_matrix.add(key)

    baseline = _mapping(suite.get("recorded_baseline"), label="suite.recorded_baseline")
    baseline_model = _text(baseline.get("model"), label="baseline.model")
    baseline_effort = _text(
        baseline.get("reasoning_effort"), label="baseline.reasoning_effort"
    )
    baseline_runs = [
        _mapping(item, label="baseline.runs[]")
        for item in _sequence(baseline.get("runs"), label="baseline.runs")
    ]
    baseline_index = _run_index(baseline_runs, label="baseline.runs")
    if set(baseline_index) != expected_matrix:
        raise ValueError("baseline run matrix does not match the suite cases")
    for key, run in baseline_index.items():
        _positive_int(run.get("duration_ms"), label=f"baseline {key}.duration_ms")
        _positive_int(run.get("total_tokens"), label=f"baseline {key}.total_tokens")
        _positive_int(run.get("tool_calls"), label=f"baseline {key}.tool_calls")
        _sha256(run.get("artifact_sha256"), label=f"baseline {key}.artifact_sha256")
        _sha256(run.get("render_set_sha256"), label=f"baseline {key}.render_set_sha256")
        if run.get("artifact_validation") != "pass":
            raise ValueError(f"baseline {key} must have passed artifact validation")

    targets = _mapping(suite.get("candidate_targets"), label="suite.candidate_targets")
    if targets.get("quality_regression_allowed") is not False:
        raise ValueError("this suite must prohibit quality regression")
    minimum_improvement = _finite_number(
        targets.get("minimum_html_median_improvement_percent"),
        label="candidate_targets.minimum_html_median_improvement_percent",
    )
    if not 0 <= minimum_improvement <= 100:
        raise ValueError("minimum HTML improvement must be between 0 and 100")
    limits_by_mode = _mapping(
        targets.get("format_ratio_limits_by_mode"),
        label="candidate_targets.format_ratio_limits_by_mode",
    )
    modes = {str(case["mode"]) for case in cases}
    if set(limits_by_mode) != modes:
        raise ValueError("format ratio limits must match the suite case modes")
    for mode in modes:
        limits = _mapping(limits_by_mode[mode], label=f"ratio limits {mode}")
        for name in ("total_tokens_max", "duration_max"):
            if (
                _finite_number(limits.get(name), label=f"ratio limits {mode}.{name}")
                <= 0
            ):
                raise ValueError(f"ratio limits {mode}.{name} must be positive")

    return {
        "cases": cases,
        "case_by_id": case_by_id,
        "required_checks": required_checks,
        "source_manifest_by_case": source_manifest_by_case,
        "baseline_manifest_by_case": baseline_manifest_by_case,
        "expected_matrix": expected_matrix,
        "baseline_index": baseline_index,
        "baseline_model": baseline_model,
        "baseline_effort": baseline_effort,
        "dimensions": dimensions,
        "reviewer_types": reviewer_types,
        "optional_reviewer_types": optional_reviewer_types,
        "score_min": score_min,
        "score_max": score_max,
        "targets": targets,
        "candidate_skill_identity": candidate_skill_identity,
        "declared_controls": frozenset(str(name) for name in controls),
        "suite_fingerprint_sha256": _canonical_sha256(suite),
    }


def _validate_candidate_run(
    run: Mapping[str, Any],
    *,
    key: tuple[str, str],
    suite_data: Mapping[str, Any],
) -> dict[str, Any]:
    label = f"candidate {key}"
    duration = _positive_int(run.get("duration_ms"), label=f"{label}.duration_ms")
    total_tokens = _positive_int(run.get("total_tokens"), label=f"{label}.total_tokens")
    input_tokens = _positive_int(run.get("input_tokens"), label=f"{label}.input_tokens")
    cached_input_tokens = _non_negative_int(
        run.get("cached_input_tokens"), label=f"{label}.cached_input_tokens"
    )
    output_tokens = _positive_int(
        run.get("output_tokens"), label=f"{label}.output_tokens"
    )
    noncached_tokens = _positive_int(
        run.get("noncached_input_plus_output_tokens"),
        label=f"{label}.noncached_input_plus_output_tokens",
    )
    tool_calls = _positive_int(run.get("tool_calls"), label=f"{label}.tool_calls")
    if total_tokens != input_tokens + output_tokens:
        raise ValueError(
            f"{label}.total_tokens must equal input_tokens + output_tokens"
        )
    if cached_input_tokens > input_tokens:
        raise ValueError(f"{label}.cached_input_tokens cannot exceed input_tokens")
    if noncached_tokens != input_tokens - cached_input_tokens + output_tokens:
        raise ValueError(f"{label} non-cached token count is inconsistent")
    if type(run.get("process_exit_code")) is not int:
        raise ValueError(f"{label}.process_exit_code must be an integer")

    identity = _mapping(run.get("execution_identity"), label=f"{label}.identity")
    model = _text(identity.get("model"), label=f"{label}.identity.model")
    effort = _text(
        identity.get("reasoning_effort"), label=f"{label}.identity.reasoning_effort"
    )
    if identity.get("enforced_by") != "codex_cli_explicit_override":
        raise ValueError(f"{label} identity was not enforced by explicit CLI override")
    skill_identity = _mapping(
        identity.get("skill_identity"), label=f"{label}.identity.skill_identity"
    )
    expected_skill = "clara" if key[1] == "HTML" else "presentations"
    if dict(skill_identity) != suite_data["candidate_skill_identity"][expected_skill]:
        raise ValueError(f"{label} skill identity does not match the sealed candidate")

    protocol = _mapping(run.get("protocol"), label=f"{label}.protocol")
    if protocol.get("ephemeral") is not True:
        raise ValueError(f"{label} must be ephemeral")
    workdir = _text(protocol.get("isolated_workdir"), label=f"{label}.workdir")
    output_root = _text(protocol.get("output_root"), label=f"{label}.output_root")
    prompt_sha = _sha256(protocol.get("prompt_sha256"), label=f"{label}.prompt_sha256")
    normalized_prompt_sha = _sha256(
        protocol.get("normalized_prompt_sha256"),
        label=f"{label}.normalized_prompt_sha256",
    )
    source_manifest_sha = _sha256(
        protocol.get("source_manifest_sha256"),
        label=f"{label}.source_manifest_sha256",
    )
    sealed_task_manifest_sha = _sha256(
        protocol.get("sealed_task_manifest_sha256"),
        label=f"{label}.sealed_task_manifest_sha256",
    )
    if protocol.get("sealed_task_verified_before_after") is not True:
        raise ValueError(f"{label} sealed task was not verified before and after")
    event_log_sha = _sha256(
        protocol.get("event_log_sha256"), label=f"{label}.event_log_sha256"
    )
    thread_id = _text(protocol.get("thread_id"), label=f"{label}.thread_id")
    if protocol.get("source_manifest_verified") is not True:
        raise ValueError(f"{label} source manifest was not verified")
    if protocol.get("read_audit") not in {"pass", "fail"}:
        raise ValueError(f"{label}.read_audit must be pass or fail")
    started_at = _timestamp(protocol.get("started_at"), label=f"{label}.started_at")
    completed_at = _timestamp(
        protocol.get("completed_at"), label=f"{label}.completed_at"
    )
    if completed_at <= started_at:
        raise ValueError(f"{label}.completed_at must follow started_at")
    if source_manifest_sha != suite_data["source_manifest_by_case"][key[0]]:
        raise ValueError(f"{label} source manifest does not match the sealed suite")

    artifact = _mapping(run.get("artifact"), label=f"{label}.artifact")
    artifact_sha = _sha256(artifact.get("sha256"), label=f"{label}.artifact.sha256")
    render_set_sha = _sha256(
        artifact.get("render_set_sha256"), label=f"{label}.artifact.render_set_sha256"
    )
    artifact_bytes = _positive_int(
        artifact.get("bytes"), label=f"{label}.artifact.bytes"
    )
    artifact_path = _text(artifact.get("path"), label=f"{label}.artifact.path")
    rendered = [
        _mapping(item, label=f"{label}.artifact.rendered_slides[]")
        for item in _sequence(
            artifact.get("rendered_slides"),
            label=f"{label}.artifact.rendered_slides",
        )
    ]
    rendered_hashes: list[str] = []
    for position, item in enumerate(rendered, start=1):
        rendered_hashes.append(
            _sha256(
                item.get("sha256"),
                label=f"{label}.rendered_slides[{position}].sha256",
            )
        )
        _positive_int(
            item.get("bytes"), label=f"{label}.rendered_slides[{position}].bytes"
        )
        _positive_int(
            item.get("width"), label=f"{label}.rendered_slides[{position}].width"
        )
        _positive_int(
            item.get("height"), label=f"{label}.rendered_slides[{position}].height"
        )
        _text(item.get("path"), label=f"{label}.rendered_slides[{position}].path")
        _text(
            item.get("renderer"),
            label=f"{label}.rendered_slides[{position}].renderer",
        )
    calculated_render_set_sha = hashlib.sha256(
        "".join(
            f"{index}\0{digest}\n"
            for index, digest in enumerate(rendered_hashes, start=1)
        ).encode("utf-8")
    ).hexdigest()
    if render_set_sha != calculated_render_set_sha:
        raise ValueError(f"{label} render-set fingerprint is invalid")

    checks = _mapping(run.get("checks"), label=f"{label}.checks")
    allowed_checks = set(
        _sequence(
            suite_data["case_by_id"][key[0]].get("required_checks_by_format")[key[1]],
            label=f"{label}.allowed_checks",
        )
    )
    if set(checks) != allowed_checks:
        missing = sorted(allowed_checks - set(checks))
        extra = sorted(set(checks) - allowed_checks)
        raise ValueError(
            f"{label} check matrix mismatch; missing={missing}, extra={extra}"
        )
    invalid_check_types = sorted(
        name for name, value in checks.items() if type(value) is not bool
    )
    if invalid_check_types:
        raise ValueError(f"{label} checks must be booleans: {invalid_check_types}")

    return {
        "duration_ms": duration,
        "total_tokens": total_tokens,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "noncached_input_plus_output_tokens": noncached_tokens,
        "tool_calls": tool_calls,
        "process_exit_code": run["process_exit_code"],
        "model": model,
        "reasoning_effort": effort,
        "workdir": workdir,
        "output_root": output_root,
        "prompt_sha256": prompt_sha,
        "normalized_prompt_sha256": normalized_prompt_sha,
        "source_manifest_sha256": source_manifest_sha,
        "sealed_task_manifest_sha256": sealed_task_manifest_sha,
        "sealed_task_verified_before_after": True,
        "event_log_sha256": event_log_sha,
        "thread_id": thread_id,
        "read_audit": protocol["read_audit"],
        "started_at": started_at,
        "completed_at": completed_at,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha,
        "render_set_sha256": render_set_sha,
        "artifact_bytes": artifact_bytes,
        "rendered_hashes": rendered_hashes,
        "checks": dict(checks),
    }


def _validate_protocol_controls(
    normalized_runs: Mapping[tuple[str, str], Mapping[str, Any]],
    *,
    suite_data: Mapping[str, Any],
) -> tuple[dict[str, bool], list[str]]:
    values = list(normalized_runs.values())
    workdirs = [str(run["workdir"]) for run in values]
    output_roots = [str(run["output_root"]) for run in values]
    models = {str(run["model"]) for run in values}
    efforts = {str(run["reasoning_effort"]) for run in values}
    thread_ids = [str(run["thread_id"]) for run in values]

    concurrent = True
    normalized_prompts = True
    same_sources = True
    for case_id in suite_data["case_by_id"]:
        html = normalized_runs[(case_id, "HTML")]
        pptx = normalized_runs[(case_id, "PPTX")]
        concurrent = concurrent and (
            html["started_at"] < pptx["completed_at"]
            and pptx["started_at"] < html["completed_at"]
        )
        normalized_prompts = normalized_prompts and (
            html["normalized_prompt_sha256"] == pptx["normalized_prompt_sha256"]
            and html["prompt_sha256"] != pptx["prompt_sha256"]
        )
        same_sources = same_sources and (
            html["source_manifest_sha256"] == pptx["source_manifest_sha256"]
        )

    controls = {
        "fresh_ephemeral_runs": len(workdirs) == len(set(workdirs))
        and len(thread_ids) == len(set(thread_ids))
        and all(
            Path(root).is_relative_to(Path(workdir))
            for root, workdir in zip(output_roots, workdirs)
        ),
        "same_model_and_reasoning_effort": models == {suite_data["baseline_model"]}
        and efforts == {suite_data["baseline_effort"]},
        "concurrent_format_runs": concurrent,
        "prompts_differ_only_by_target_format": normalized_prompts,
        "no_prior_run_or_opposite_format_reads": all(
            run["read_audit"] == "pass" for run in values
        ),
        "same_source_package": same_sources,
        "sealed_inputs_immutable": all(
            run["sealed_task_verified_before_after"] is True for run in values
        ),
    }
    failures = sorted(name for name, passed in controls.items() if not passed)
    if set(controls) != set(suite_data["declared_controls"]):
        raise ValueError("runner protocol controls do not match the suite contract")
    return controls, failures


def _semantic_review_failures(
    candidate: Mapping[str, Any],
    *,
    candidate_runs: Mapping[tuple[str, str], Mapping[str, Any]],
    suite_data: Mapping[str, Any],
    packet_mappings: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[str]:
    reviews = [
        _mapping(item, label="candidate.semantic_reviews[]")
        for item in _sequence(
            candidate.get("semantic_reviews"), label="candidate.semantic_reviews"
        )
    ]
    grouped: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = {}
    builder_thread_ids = {str(run["thread_id"]) for run in candidate_runs.values()}
    model_reviewer_thread_ids: set[str] = set()
    for position, review in enumerate(reviews, start=1):
        if "dimensions" in review or "overall_non_regression" in review:
            raise ValueError(
                "semantic reviews must retain raw A/B scores without manual unblinding"
            )
        case_id = _text(
            review.get("case_id"), label=f"semantic review {position}.case_id"
        )
        output_format = _text(
            review.get("format"), label=f"semantic review {position}.format"
        ).upper()
        key = (case_id, output_format)
        if key not in candidate_runs:
            raise ValueError(f"semantic review {position} references unknown run {key}")
        reviewer = _mapping(
            review.get("reviewer"), label=f"semantic review {position}.reviewer"
        )
        reviewer_type = _text(
            reviewer.get("type"), label=f"semantic review {position}.reviewer.type"
        )
        allowed_reviewer_types = set(suite_data["reviewer_types"]) | set(
            suite_data["optional_reviewer_types"]
        )
        if reviewer_type not in allowed_reviewer_types:
            raise ValueError(f"semantic review {position} has invalid reviewer type")
        _text(reviewer.get("id"), label=f"semantic review {position}.reviewer.id")
        if reviewer_type == "model":
            _text(
                reviewer.get("model"),
                label=f"semantic review {position}.reviewer.model",
            )
        elif reviewer.get("model") not in {None, ""}:
            raise ValueError("human semantic reviews must not claim a model identity")
        packet = packet_mappings.get(key)
        if packet is None:
            raise ValueError(f"semantic review {position} has no runner packet mapping")
        if review.get("review_packet_id") != packet["packet_id"]:
            raise ValueError(f"semantic review {position} packet ID mismatch")
        if (
            _sha256(
                review.get("review_prompt_sha256"),
                label=f"semantic review {position}.review_prompt_sha256",
            )
            != packet["prompt_sha256"]
        ):
            raise ValueError(f"semantic review {position} prompt hash mismatch")
        if (
            _sha256(
                review.get("source_requirements_sha256"),
                label=f"semantic review {position}.source_requirements_sha256",
            )
            != packet["source_requirements_sha256"]
        ):
            raise ValueError(
                f"semantic review {position} source requirements hash mismatch"
            )
        reviewer_thread_id = _text(
            reviewer.get("thread_id"),
            label=f"semantic review {position}.reviewer.thread_id",
        )
        if reviewer_thread_id in builder_thread_ids:
            raise ValueError("semantic reviewer threads must be disjoint from builders")
        if reviewer_type == "model":
            if reviewer_thread_id in model_reviewer_thread_ids:
                raise ValueError("model reviewer threads must be unique across packets")
            model_reviewer_thread_ids.add(reviewer_thread_id)
        if reviewer_type in grouped.setdefault(key, {}):
            raise ValueError(f"duplicate {reviewer_type} semantic review for {key}")
        grouped[key][reviewer_type] = review

    failures: list[str] = []
    for key, run in candidate_runs.items():
        required_types = set(suite_data["reviewer_types"])
        run_reviews = grouped.get(key, {})
        missing_types = sorted(required_types - set(run_reviews))
        for reviewer_type in missing_types:
            failures.append(f"{key[0]}:{key[1]}:missing_{reviewer_type}_review")
        for reviewer_type, review in run_reviews.items():
            candidate_hash = _sha256(
                review.get("candidate_artifact_sha256"),
                label=f"semantic review {key} candidate artifact",
            )
            baseline_hash = _sha256(
                review.get("baseline_artifact_sha256"),
                label=f"semantic review {key} baseline artifact",
            )
            if candidate_hash != run["artifact_sha256"]:
                raise ValueError(
                    f"semantic review {key} candidate artifact hash mismatch"
                )
            expected_baseline_hash = _sha256(
                suite_data["baseline_index"][key].get("artifact_sha256"),
                label=f"baseline {key}.artifact_sha256",
            )
            if baseline_hash != expected_baseline_hash:
                raise ValueError(
                    f"semantic review {key} baseline artifact hash mismatch"
                )
            candidate_render_hash = _sha256(
                review.get("candidate_render_set_sha256"),
                label=f"semantic review {key} candidate render set",
            )
            baseline_render_hash = _sha256(
                review.get("baseline_render_set_sha256"),
                label=f"semantic review {key} baseline render set",
            )
            packet = packet_mappings[key]
            if (
                candidate_render_hash != run["render_set_sha256"]
                or candidate_render_hash != packet["candidate_render_set_sha256"]
            ):
                raise ValueError(f"semantic review {key} candidate render-set mismatch")
            if baseline_render_hash != packet["baseline_render_set_sha256"]:
                raise ValueError(f"semantic review {key} baseline render-set mismatch")

            scores_by_label = _mapping(
                review.get("scores_by_label"),
                label=f"semantic review {key} {reviewer_type}.scores_by_label",
            )
            if set(scores_by_label) != {"A", "B"}:
                raise ValueError(
                    f"semantic review {key} {reviewer_type} must retain A/B scores"
                )
            normalized_scores: dict[str, dict[str, Mapping[str, Any]]] = {}
            for label_name in ("A", "B"):
                label_scores = _mapping(
                    scores_by_label[label_name],
                    label=(
                        f"semantic review {key} {reviewer_type}."
                        f"scores_by_label.{label_name}"
                    ),
                )
                if set(label_scores) != set(suite_data["dimensions"]):
                    raise ValueError(
                        f"semantic review {key} {reviewer_type} "
                        f"{label_name} dimension matrix mismatch"
                    )
                normalized_scores[label_name] = {
                    dimension: _mapping(
                        label_scores[dimension],
                        label=(
                            f"semantic review {key} {reviewer_type}."
                            f"{label_name}.{dimension}"
                        ),
                    )
                    for dimension in suite_data["dimensions"]
                }
            review_failed = False
            _text(
                review.get("overall_rationale"),
                label=f"semantic review {key} {reviewer_type}.overall_rationale",
            )
            for dimension in suite_data["dimensions"]:
                candidate_result = normalized_scores[str(packet["candidate_label"])][
                    dimension
                ]
                baseline_result = normalized_scores[str(packet["baseline_label"])][
                    dimension
                ]
                baseline_score = _finite_number(
                    baseline_result.get("score"),
                    label=f"semantic review {key} {dimension}.baseline_label_score",
                )
                candidate_score = _finite_number(
                    candidate_result.get("score"),
                    label=f"semantic review {key} {dimension}.candidate_label_score",
                )
                for score_name, score in (
                    ("baseline_score", baseline_score),
                    ("candidate_score", candidate_score),
                ):
                    if not suite_data["score_min"] <= score <= suite_data["score_max"]:
                        raise ValueError(
                            f"semantic review {key} {dimension}.{score_name} is outside the scale"
                        )
                if (
                    type(candidate_result.get("pass")) is not bool
                    or type(baseline_result.get("pass")) is not bool
                ):
                    raise ValueError(
                        f"semantic review {key} {dimension} label passes must be booleans"
                    )
                _text(
                    candidate_result.get("rationale"),
                    label=f"semantic review {key} {dimension}.candidate_rationale",
                )
                _text(
                    baseline_result.get("rationale"),
                    label=f"semantic review {key} {dimension}.baseline_rationale",
                )
                if (
                    candidate_result["pass"] is not True
                    or candidate_score < baseline_score
                ):
                    review_failed = True
            if review_failed:
                failures.append(
                    f"{key[0]}:{key[1]}:{reviewer_type}_semantic_regression"
                )
    return sorted(failures)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4)


def _improvement(candidate: int, baseline: int) -> float:
    return round(((baseline - candidate) / baseline) * 100.0, 1)


def summarize_benchmark(
    suite: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare runner-produced candidate runs with the sealed baseline and targets."""

    suite_data = validate_suite(suite)
    if candidate.get("schema_version") != RUN_SCHEMA:
        raise ValueError("unsupported benchmark run schema")
    if candidate.get("suite_id") != suite.get("suite_id"):
        raise ValueError("candidate suite_id does not match the benchmark suite")
    evidence = _mapping(
        candidate.get("protocol_evidence"), label="candidate.protocol_evidence"
    )
    if evidence.get("producer") != "run_clara_deck_benchmark.py":
        raise ValueError("candidate records must be produced by the benchmark runner")
    if (
        _sha256(
            evidence.get("suite_fingerprint_sha256"),
            label="candidate.protocol_evidence.suite_fingerprint_sha256",
        )
        != suite_data["suite_fingerprint_sha256"]
    ):
        raise ValueError("candidate suite fingerprint does not match")
    _text(
        evidence.get("codex_cli_version"),
        label="candidate.protocol_evidence.codex_cli_version",
    )
    evidence_skill_identity = _mapping(
        evidence.get("candidate_skill_identity"),
        label="candidate.protocol_evidence.candidate_skill_identity",
    )
    if dict(evidence_skill_identity) != suite_data["candidate_skill_identity"]:
        raise ValueError("candidate protocol skill identity does not match the suite")
    skill_paths = _mapping(
        evidence.get("candidate_skill_paths"),
        label="candidate.protocol_evidence.candidate_skill_paths",
    )
    if set(skill_paths) != {"clara_root", "presentations_root"}:
        raise ValueError("candidate skill paths must bind Clara and Presentations")
    clara_path = Path(
        _text(skill_paths["clara_root"], label="candidate Clara skill path")
    )
    presentations_path = Path(
        _text(
            skill_paths["presentations_root"],
            label="candidate Presentations skill path",
        )
    )
    if clara_path.name != suite_data["candidate_skill_identity"]["clara"]["version"]:
        raise ValueError("candidate Clara path does not bind the sealed version")
    if (
        suite_data["candidate_skill_identity"]["presentations"]["version"]
        not in presentations_path.parts
    ):
        raise ValueError(
            "candidate Presentations path does not bind the sealed version"
        )
    baseline_manifests = _mapping(
        evidence.get("baseline_evidence_manifests"),
        label="candidate.protocol_evidence.baseline_evidence_manifests",
    )
    if dict(baseline_manifests) != suite_data["baseline_manifest_by_case"]:
        raise ValueError("candidate baseline evidence manifests do not match the suite")
    raw_packet_mappings = [
        _mapping(item, label="protocol_evidence.review_packet_mappings[]")
        for item in _sequence(
            evidence.get("review_packet_mappings"),
            label="protocol_evidence.review_packet_mappings",
        )
    ]
    packet_mappings: dict[tuple[str, str], Mapping[str, Any]] = {}
    for mapping in raw_packet_mappings:
        key = (
            _text(mapping.get("case_id"), label="review packet case_id"),
            _text(mapping.get("format"), label="review packet format").upper(),
        )
        if key in packet_mappings:
            raise ValueError(f"duplicate review packet mapping for {key}")
        if {mapping.get("candidate_label"), mapping.get("baseline_label")} != {
            "A",
            "B",
        }:
            raise ValueError(f"review packet {key} must randomize labels A and B")
        for field in (
            "prompt_sha256",
            "source_requirements_sha256",
            "candidate_render_set_sha256",
            "baseline_render_set_sha256",
        ):
            _sha256(mapping.get(field), label=f"review packet {key}.{field}")
        _text(mapping.get("packet_id"), label=f"review packet {key}.packet_id")
        packet_mappings[key] = mapping

    candidate_runs = [
        _mapping(item, label="candidate.runs[]")
        for item in _sequence(candidate.get("runs"), label="candidate.runs")
    ]
    candidate_index = _run_index(candidate_runs, label="candidate.runs")
    expected_matrix = set(suite_data["expected_matrix"])
    if set(candidate_index) != expected_matrix:
        missing = sorted(expected_matrix - set(candidate_index))
        extra = sorted(set(candidate_index) - expected_matrix)
        raise ValueError(
            f"candidate run matrix mismatch; missing={missing}, extra={extra}"
        )
    normalized_runs = {
        key: _validate_candidate_run(run, key=key, suite_data=suite_data)
        for key, run in candidate_index.items()
    }
    if set(packet_mappings) != set(normalized_runs):
        raise ValueError("review packet matrix does not match candidate runs")
    for key, mapping in packet_mappings.items():
        if (
            mapping["candidate_render_set_sha256"]
            != normalized_runs[key]["render_set_sha256"]
        ):
            raise ValueError(f"review packet {key} is not bound to candidate renders")
    control_checks, failed_controls = _validate_protocol_controls(
        normalized_runs, suite_data=suite_data
    )
    semantic_failures = _semantic_review_failures(
        candidate,
        candidate_runs=normalized_runs,
        suite_data=suite_data,
        packet_mappings=packet_mappings,
    )

    comparisons: dict[str, Any] = {}
    html_token_improvements: list[float] = []
    html_duration_improvements: list[float] = []
    mechanical_failures: list[str] = []
    for case_id, case in suite_data["case_by_id"].items():
        case_result: dict[str, Any] = {"mode": case["mode"]}
        for output_format in ("HTML", "PPTX"):
            key = (case_id, output_format)
            run = normalized_runs[key]
            baseline = suite_data["baseline_index"][key]
            failed_checks = sorted(
                name for name, passed in run["checks"].items() if passed is not True
            )
            passed = run["process_exit_code"] == 0 and not failed_checks
            if not passed:
                mechanical_failures.append(f"{case_id}:{output_format}")
            duration_improvement = _improvement(
                run["duration_ms"], int(baseline["duration_ms"])
            )
            token_improvement = _improvement(
                run["total_tokens"], int(baseline["total_tokens"])
            )
            case_result[output_format] = {
                "duration_ms": run["duration_ms"],
                "total_tokens": run["total_tokens"],
                "output_tokens": run["output_tokens"],
                "noncached_input_plus_output_tokens": run[
                    "noncached_input_plus_output_tokens"
                ],
                "tool_calls": run["tool_calls"],
                "duration_improvement_vs_baseline_percent": duration_improvement,
                "token_improvement_vs_baseline_percent": token_improvement,
                "artifact_sha256": run["artifact_sha256"],
                "artifact_validation": "pass" if passed else "fail",
                "required_checks": list(suite_data["required_checks"][key]),
                "failed_checks": failed_checks,
            }
            if output_format == "HTML":
                html_token_improvements.append(token_improvement)
                html_duration_improvements.append(duration_improvement)
        case_result["html_to_pptx"] = {
            "duration_ratio": _ratio(
                case_result["HTML"]["duration_ms"],
                case_result["PPTX"]["duration_ms"],
            ),
            "total_tokens_ratio": _ratio(
                case_result["HTML"]["total_tokens"],
                case_result["PPTX"]["total_tokens"],
            ),
            "output_tokens_ratio": _ratio(
                case_result["HTML"]["output_tokens"],
                case_result["PPTX"]["output_tokens"],
            ),
            "noncached_input_plus_output_tokens_ratio": _ratio(
                case_result["HTML"]["noncached_input_plus_output_tokens"],
                case_result["PPTX"]["noncached_input_plus_output_tokens"],
            ),
            "tool_calls_ratio": _ratio(
                case_result["HTML"]["tool_calls"],
                case_result["PPTX"]["tool_calls"],
            ),
        }
        comparisons[case_id] = case_result

    median_token_improvement = round(statistics.median(html_token_improvements), 1)
    median_duration_improvement = round(
        statistics.median(html_duration_improvements), 1
    )
    minimum_improvement = _finite_number(
        suite_data["targets"]["minimum_html_median_improvement_percent"],
        label="minimum_html_median_improvement_percent",
    )
    target_checks: dict[str, bool] = {
        "protocol_controls": not failed_controls,
        "mechanical_quality": not mechanical_failures,
        "semantic_non_regression": not semantic_failures,
        "html_median_token_improvement": median_token_improvement
        >= minimum_improvement,
        "html_median_duration_improvement": median_duration_improvement
        >= minimum_improvement,
    }
    ratio_limits = suite_data["targets"]["format_ratio_limits_by_mode"]
    for case_id, case_result in comparisons.items():
        mode = str(case_result["mode"])
        limits = _mapping(ratio_limits[mode], label=f"ratio limits {mode}")
        target_checks[f"{mode}_token_ratio"] = case_result["html_to_pptx"][
            "total_tokens_ratio"
        ] <= _finite_number(
            limits["total_tokens_max"], label=f"ratio limits {mode}.total_tokens_max"
        )
        target_checks[f"{mode}_duration_ratio"] = case_result["html_to_pptx"][
            "duration_ratio"
        ] <= _finite_number(
            limits["duration_max"], label=f"ratio limits {mode}.duration_max"
        )

    quality_failures = sorted(set(mechanical_failures + semantic_failures))
    return {
        "schema_version": SUMMARY_SCHEMA,
        "suite_id": suite["suite_id"],
        "result": "pass" if all(target_checks.values()) else "fail",
        "protocol_controls": control_checks,
        "failed_controls": failed_controls,
        "mechanical_failures": mechanical_failures,
        "semantic_failures": semantic_failures,
        "quality_failures": quality_failures,
        "html_median_improvement": {
            "tokens_percent": median_token_improvement,
            "duration_percent": median_duration_improvement,
        },
        "comparisons": comparisons,
        "target_checks": target_checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        suite = json.loads(
            args.suite.expanduser().resolve().read_text(encoding="utf-8")
        )
        runs = json.loads(args.runs.expanduser().resolve().read_text(encoding="utf-8"))
        report = summarize_benchmark(
            _mapping(suite, label="suite"), _mapping(runs, label="runs")
        )
        rendered = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if args.output:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
            LOGGER.info("Wrote Clara HTML benchmark summary to %s", output)
        else:
            sys.stdout.write(rendered)
        return 0 if report["result"] == "pass" else 1
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        LOGGER.error("error: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
