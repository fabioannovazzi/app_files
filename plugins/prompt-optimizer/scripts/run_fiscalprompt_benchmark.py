#!/usr/bin/env python3
"""Prepare and optionally execute a blinded Prompt Optimizer benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "build_review_packets",
    "extract_fiscalprompt_template",
    "parse_codex_jsonl",
    "prepare_benchmark",
    "run_prepared_benchmark",
    "validate_suite",
]

LOGGER = logging.getLogger(__name__)
SUITE_SCHEMA = "prompt_optimizer.fiscalprompt_benchmark_suite.v1"
PLAN_SCHEMA = "prompt_optimizer.fiscalprompt_benchmark_plan.v1"
RUNS_SCHEMA = "prompt_optimizer.fiscalprompt_benchmark_runs.v1"
REVIEW_SCHEMA = "prompt_optimizer.fiscalprompt_benchmark_review.v1"
TREATMENTS = ("optimize_prompt", "fiscalprompt")
TOOL_ITEM_TYPES = {
    "command_execution",
    "computer_use",
    "file_change",
    "image_generation",
    "mcp_tool_call",
    "web_search",
}
TOOL_INVOCATION_FIELDS = {
    "action",
    "arguments",
    "command",
    "cwd",
    "input",
    "path",
    "paths",
    "query",
    "url",
}
REQUIRED_TEMPLATE_SECTIONS = (
    "RUOLO",
    "CONTESTO",
    "OBIETTIVO",
    "OUTPUT RICHIESTO",
    "VINCOLI PROFESSIONALI",
)
CODEX_DISABLED_FEATURES = (
    "plugins",
    "skill_search",
    "plugin_sharing",
    "remote_plugin",
)
PROMPT_OPTIMIZER_PATH_COMPONENT = re.compile(
    r"(?:^|[/\\])prompt[-_]optimizer(?:[/\\]|$)", re.IGNORECASE
)


@dataclass(frozen=True)
class PreparedRun:
    """One isolated benchmark treatment run."""

    case_id: str
    repeat: int
    treatment: str
    workdir: Path
    task_root: Path
    task_sha256: str
    prompt: str


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _tree_sha256(root: Path) -> str:
    """Hash task bytes for reproducible preparation and mutation detection."""

    rows: list[str] = []
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        if path.is_symlink():
            raise ValueError(f"task tree contains a symlink: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            rows.append(f"{relative}\0{_sha256_file(path)}\n")
    if not rows:
        raise ValueError("task tree must contain files")
    return _sha256_bytes("".join(rows).encode("utf-8"))


def _seal_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)


def validate_suite(suite: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the semantic benchmark contract without judging tax meaning."""

    if suite.get("schema_version") != SUITE_SCHEMA:
        raise ValueError("unsupported FiscalPrompt benchmark suite schema")
    suite_id = _text(suite.get("suite_id"), label="suite_id")
    repeats = suite.get("repeats_per_case")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("repeats_per_case must be a positive integer")

    rubric = _mapping(suite.get("rubric"), label="rubric")
    rubric_dimensions: dict[str, tuple[str, ...]] = {}
    for artifact_kind in ("prompt", "answer"):
        dimensions = _sequence(
            rubric.get(f"{artifact_kind}_dimensions"),
            label=f"rubric.{artifact_kind}_dimensions",
        )
        ids: list[str] = []
        total_weight = 0.0
        for position, raw in enumerate(dimensions):
            dimension = _mapping(
                raw, label=f"rubric.{artifact_kind}_dimensions[{position}]"
            )
            dimension_id = _text(dimension.get("id"), label="dimension.id")
            weight = dimension.get("weight")
            if not isinstance(weight, (int, float)) or isinstance(weight, bool):
                raise ValueError(f"weight for {dimension_id} must be numeric")
            if not 0 < float(weight) <= 1:
                raise ValueError(f"weight for {dimension_id} must be in (0, 1]")
            ids.append(dimension_id)
            total_weight += float(weight)
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate {artifact_kind} rubric dimension")
        if abs(total_weight - 1.0) > 1e-9:
            raise ValueError(f"{artifact_kind} rubric weights must sum to 1")
        rubric_dimensions[artifact_kind] = tuple(ids)

    reviewer_policy = _mapping(suite.get("reviewer_policy"), label="reviewer_policy")
    required_reviewers = tuple(
        _text(value, label="required_reviewer_types[]")
        for value in _sequence(
            reviewer_policy.get("required_reviewer_types"),
            label="reviewer_policy.required_reviewer_types",
        )
    )
    if "tax_professional" not in required_reviewers:
        raise ValueError("tax_professional review is required for this benchmark")

    cases = _sequence(suite.get("cases"), label="cases")
    if not cases:
        raise ValueError("benchmark suite must contain cases")
    case_ids: list[str] = []
    normalized_cases: list[dict[str, Any]] = []
    for position, raw in enumerate(cases):
        case = dict(_mapping(raw, label=f"cases[{position}]"))
        case_id = _text(case.get("id"), label=f"cases[{position}].id")
        template_id = _text(
            case.get("fiscalprompt_template_id"),
            label=f"cases[{position}].fiscalprompt_template_id",
        )
        _text(case.get("question"), label=f"cases[{position}].question")
        _text(case.get("jurisdiction"), label=f"cases[{position}].jurisdiction")
        _text(case.get("output_language"), label=f"cases[{position}].output_language")
        anchors = [
            _text(value, label=f"cases[{position}].fact_anchors[]")
            for value in _sequence(
                case.get("fact_anchors"), label=f"cases[{position}].fact_anchors"
            )
        ]
        if not anchors:
            raise ValueError(f"case {case_id} must declare fact anchors")
        case["id"] = case_id
        case["fiscalprompt_template_id"] = template_id
        case["fact_anchors"] = anchors
        case_ids.append(case_id)
        normalized_cases.append(case)
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark case IDs must be unique")
    return {
        "suite_id": suite_id,
        "repeats": repeats,
        "cases": normalized_cases,
        "rubric_dimensions": rubric_dimensions,
        "required_reviewer_types": required_reviewers,
    }


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract layout text mechanically; legal relevance is not inferred here."""

    executable = shutil.which("pdftotext")
    if executable is None:
        raise RuntimeError("pdftotext is required to extract FiscalPrompt templates")
    completed = subprocess.run(
        [executable, "-layout", str(pdf_path), "-"],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"pdftotext failed: {error}")
    return completed.stdout.decode("utf-8", errors="replace")


def extract_fiscalprompt_template(pdf_text: str, template_id: str) -> str:
    """Extract one explicitly selected template from a form-feed-delimited page."""

    identifier = template_id.strip()
    if not identifier:
        raise ValueError("template_id is required")
    pattern = re.compile(rf"(?m)^\s*{re.escape(identifier)}\s*[\u2013\u2014-]")
    matches: list[tuple[int, str]] = []
    for page_number, page in enumerate(pdf_text.split("\f"), start=1):
        match = pattern.search(page)
        if match is None:
            continue
        template = page[match.start() :].strip()
        matches.append((page_number, template))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one page for template {identifier!r}; found {len(matches)}"
        )
    page_number, template = matches[0]
    normalized_upper = template.upper()
    missing = [
        section
        for section in REQUIRED_TEMPLATE_SECTIONS
        if section not in normalized_upper
    ]
    if missing:
        raise ValueError(
            f"template {identifier!r} on PDF page {page_number} is missing sections: "
            + ", ".join(missing)
        )
    return template + "\n"


def _public_case(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in case.items()
        if key not in {"fiscalprompt_template_id", "review_focus"}
    }


def _common_output_contract() -> str:
    return """Write these files under result/:
- answer.md: the final Italian professional answer, maximum 1,800 words.
- prompt_used.md: the complete prompt or generation instructions actually used.
- sources.json: a JSON array of objects with url, title, source_class, and supported_claims.

Do not put treatment names, benchmark labels, or comparisons in those files.
Use only facts in task/case.json. Research current law as of the case's as_of_date.
Prefer official and primary sources. Never invent legislation, cases, circulars, or URLs.
If a material point cannot be verified, state that limitation explicitly.
"""


def _optimizer_instructions(skill_path: Path) -> str:
    return f"""# Benchmark treatment instructions

Read task/case.json. Use the Prompt Optimizer specification at:
{skill_path}

Treat prompt optimization as the internal planning stage, then use the resulting
instructions to answer the case. Do not inspect or search for FiscalPrompt, its PDF,
its templates, the opposite treatment directory, or another benchmark run.

{_common_output_contract()}"""


def _fiscalprompt_instructions() -> str:
    return f"""# Benchmark treatment instructions

Read task/fiscalprompt_template.md and task/case.json. Use the supplied template as
the professional instruction framework and apply the case facts to its placeholders.
Do not use, inspect, or search for the Prompt Optimizer plugin, skill, outputs, the
opposite treatment directory, or another benchmark run.

{_common_output_contract()}"""


def _launch_prompt() -> str:
    return (
        "Read task/instructions.md and task/case.json, complete the treatment, "
        "and write every required artifact under result/."
    )


def _prepare_run(
    *,
    output_root: Path,
    case: Mapping[str, Any],
    repeat: int,
    treatment: str,
    optimizer_skill_path: Path,
    template: str,
) -> PreparedRun:
    task_root = (
        output_root
        / "sealed_tasks"
        / str(case["id"])
        / f"repeat-{repeat:02d}"
        / treatment
    )
    workdir = (
        output_root / "runs" / str(case["id"]) / f"repeat-{repeat:02d}" / treatment
    )
    task_root.mkdir(parents=True)
    workdir.mkdir(parents=True)
    (workdir / "result").mkdir()
    _write_json(task_root / "case.json", _public_case(case))
    instructions = (
        _optimizer_instructions(optimizer_skill_path)
        if treatment == "optimize_prompt"
        else _fiscalprompt_instructions()
    )
    (task_root / "instructions.md").write_text(instructions + "\n", encoding="utf-8")
    if treatment == "fiscalprompt":
        (task_root / "fiscalprompt_template.md").write_text(template, encoding="utf-8")
    task_sha256 = _tree_sha256(task_root)
    _seal_tree(task_root)
    (workdir / "task").symlink_to(task_root.resolve(), target_is_directory=True)
    prompt = _launch_prompt()
    (workdir / "run_prompt.md").write_text(prompt + "\n", encoding="utf-8")
    return PreparedRun(
        case_id=str(case["id"]),
        repeat=repeat,
        treatment=treatment,
        workdir=workdir.resolve(),
        task_root=task_root.resolve(),
        task_sha256=task_sha256,
        prompt=prompt,
    )


def prepare_benchmark(
    suite: Mapping[str, Any],
    *,
    pdf_path: Path,
    output_root: Path,
    optimizer_skill_path: Path,
    repo_root: Path | None = None,
) -> list[PreparedRun]:
    """Prepare sealed paired tasks while keeping purchased text outside git."""

    validated = validate_suite(suite)
    repository = (repo_root or Path(__file__).resolve().parents[3]).resolve()
    output = output_root.expanduser().resolve()
    pdf = pdf_path.expanduser().resolve()
    skill = optimizer_skill_path.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"output root already exists: {output}")
    if _is_within(output, repository):
        raise ValueError("benchmark run outputs must be outside the Git workspace")
    if _is_within(pdf, repository):
        raise ValueError("the purchased FiscalPrompt PDF must remain outside git")
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    if not skill.is_file():
        raise FileNotFoundError(skill)

    pdf_text = _extract_pdf_text(pdf)
    templates: dict[str, str] = {}
    for case in validated["cases"]:
        template_id = str(case["fiscalprompt_template_id"])
        templates.setdefault(
            template_id, extract_fiscalprompt_template(pdf_text, template_id)
        )

    output.mkdir(parents=True)
    prepared: list[PreparedRun] = []
    launch_order: list[dict[str, Any]] = []
    for case in validated["cases"]:
        for repeat in range(1, int(validated["repeats"]) + 1):
            order = list(TREATMENTS)
            secrets.SystemRandom().shuffle(order)
            launch_order.append(
                {"case_id": case["id"], "repeat": repeat, "treatments": order}
            )
            for treatment in TREATMENTS:
                prepared.append(
                    _prepare_run(
                        output_root=output,
                        case=case,
                        repeat=repeat,
                        treatment=treatment,
                        optimizer_skill_path=skill,
                        template=templates[str(case["fiscalprompt_template_id"])],
                    )
                )

    plan = {
        "schema_version": PLAN_SCHEMA,
        "suite_id": validated["suite_id"],
        "suite_fingerprint_sha256": _canonical_sha256(suite),
        "created_at": _iso_now(),
        "producer": Path(__file__).name,
        "source_receipt": {
            "pdf_path": str(pdf),
            "pdf_sha256": _sha256_file(pdf),
            "pdf_copied_into_git": False,
            "extracted_templates_stored_only_under_external_output_root": True,
        },
        "candidate_identity": {
            "skill_path": str(skill),
            "skill_sha256": _sha256_file(skill),
        },
        "launch_order": launch_order,
        "runs": [
            {
                "case_id": run.case_id,
                "repeat": run.repeat,
                "treatment": run.treatment,
                "workdir": str(run.workdir),
                "task_root": str(run.task_root),
                "task_sha256": run.task_sha256,
                "run_prompt_sha256": _sha256_bytes(run.prompt.encode("utf-8")),
            }
            for run in prepared
        ],
    }
    _write_json(output / "benchmark_plan.json", plan)
    LOGGER.info("Prepared %s benchmark runs under %s", len(prepared), output)
    return prepared


def _load_prepared(output_root: Path, suite: Mapping[str, Any]) -> list[PreparedRun]:
    plan_path = output_root / "benchmark_plan.json"
    plan = _mapping(json.loads(plan_path.read_text(encoding="utf-8")), label="plan")
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("unsupported prepared benchmark plan")
    if plan.get("suite_fingerprint_sha256") != _canonical_sha256(suite):
        raise ValueError("prepared plan does not match the current suite")
    candidate = _mapping(plan.get("candidate_identity"), label="candidate_identity")
    skill_path = Path(_text(candidate.get("skill_path"), label="skill_path"))
    if not skill_path.is_file() or _sha256_file(skill_path) != candidate.get(
        "skill_sha256"
    ):
        raise ValueError("Prompt Optimizer skill changed after benchmark preparation")

    prepared: list[PreparedRun] = []
    for raw in _sequence(plan.get("runs"), label="plan.runs"):
        record = _mapping(raw, label="plan.runs[]")
        workdir = Path(_text(record.get("workdir"), label="workdir"))
        task_root = Path(_text(record.get("task_root"), label="task_root"))
        observed = _tree_sha256(task_root)
        expected = _text(record.get("task_sha256"), label="task_sha256")
        if observed != expected:
            raise ValueError(f"sealed benchmark task changed: {task_root}")
        prompt = (workdir / "run_prompt.md").read_text(encoding="utf-8").strip()
        prepared.append(
            PreparedRun(
                case_id=_text(record.get("case_id"), label="case_id"),
                repeat=int(record["repeat"]),
                treatment=_text(record.get("treatment"), label="treatment"),
                workdir=workdir,
                task_root=task_root,
                task_sha256=expected,
                prompt=prompt,
            )
        )
    return prepared


def parse_codex_jsonl(payload: bytes) -> dict[str, Any]:
    """Extract recorded usage and tool activity from Codex JSONL."""

    events: list[Mapping[str, Any]] = []
    for line_number, raw_line in enumerate(payload.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid Codex JSONL at line {line_number}") from exc
        events.append(_mapping(event, label=f"Codex event {line_number}"))
    if not events:
        raise ValueError("Codex emitted no JSONL events")

    usage: Mapping[str, Any] | None = None
    thread_id = ""
    tool_ids: set[str] = set()
    tool_inputs: list[str] = []
    for event in events:
        if isinstance(event.get("thread_id"), str):
            thread_id = str(event["thread_id"])
        if isinstance(event.get("usage"), Mapping):
            usage = _mapping(event["usage"], label="usage")
        item = event.get("item")
        if not isinstance(item, Mapping):
            continue
        item_type = str(item.get("type", ""))
        if item_type not in TOOL_ITEM_TYPES:
            continue
        item_id = str(item.get("id") or f"tool-{len(tool_ids) + 1}")
        tool_ids.add(item_id)
        invocation = {key: item[key] for key in TOOL_INVOCATION_FIELDS if key in item}
        if invocation:
            tool_inputs.append(
                json.dumps(invocation, ensure_ascii=False, sort_keys=True)
            )
    if usage is None:
        raise ValueError("Codex JSONL contains no usage record")
    values: dict[str, int] = {}
    for name, allow_zero in (
        ("input_tokens", False),
        ("cached_input_tokens", True),
        ("output_tokens", False),
    ):
        value = usage.get(name, 0 if allow_zero else None)
        if type(value) is not int or value < (0 if allow_zero else 1):
            raise ValueError(f"Codex usage.{name} must be an integer")
        values[name] = value
    return {
        "thread_id": thread_id,
        **values,
        "total_tokens": values["input_tokens"] + values["output_tokens"],
        "noncached_tokens": (
            values["input_tokens"]
            - values["cached_input_tokens"]
            + values["output_tokens"]
        ),
        "tool_calls": len(tool_ids),
        "tool_inputs": tool_inputs,
    }


def _verify_task(run: PreparedRun) -> None:
    task_link = run.workdir / "task"
    if not task_link.is_symlink() or task_link.resolve() != run.task_root.resolve():
        raise ValueError(f"task link changed for {run.case_id}:{run.treatment}")
    if _tree_sha256(run.task_root) != run.task_sha256:
        raise ValueError(f"task bytes changed for {run.case_id}:{run.treatment}")


def _launch_run(
    run: PreparedRun, *, codex_bin: str, model: str, reasoning_effort: str
) -> dict[str, Any]:
    _verify_task(run)
    command = [
        codex_bin,
        "exec",
        "--json",
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-user-config",
    ]
    for feature in CODEX_DISABLED_FEATURES:
        command.extend(("--disable", feature))
    command.extend(
        [
            "--model",
            model,
            "--config",
            f'model_reasoning_effort="{reasoning_effort}"',
            "--sandbox",
            "workspace-write",
            "--cd",
            str(run.workdir),
            "--output-last-message",
            str(run.workdir / "codex_last_message.txt"),
            "-",
        ]
    )
    started_at = _iso_now()
    started = time.monotonic()
    process = subprocess.run(
        command,
        input=run.prompt.encode("utf-8"),
        capture_output=True,
        check=False,
        timeout=3600,
    )
    duration_ms = max(1, round((time.monotonic() - started) * 1000))
    (run.workdir / "codex_events.jsonl").write_bytes(process.stdout)
    (run.workdir / "codex_stderr.txt").write_bytes(process.stderr)
    _verify_task(run)
    metrics = parse_codex_jsonl(process.stdout)
    return {
        "run": run,
        "process_exit_code": process.returncode,
        "duration_ms": duration_ms,
        "started_at": started_at,
        "completed_at": _iso_now(),
        "metrics": metrics,
    }


def _artifact_record(run: PreparedRun, filename: str) -> dict[str, Any]:
    path = run.workdir / "result" / filename
    return {
        "path": str(path),
        "exists": path.is_file(),
        "sha256": _sha256_file(path) if path.is_file() else None,
        "bytes": path.stat().st_size if path.is_file() else 0,
    }


def _sources_json_valid(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, list):
        return False
    required_fields = {"url", "title", "source_class", "supported_claims"}
    return bool(payload) and all(
        isinstance(item, Mapping)
        and set(item) >= required_fields
        and isinstance(item["url"], str)
        and item["url"].startswith(("https://", "http://"))
        for item in payload
    )


def _audit_treatment_isolation(
    run: PreparedRun,
    *,
    metrics: Mapping[str, Any],
    all_runs: Sequence[PreparedRun],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit tool inputs mechanically for forbidden cross-treatment reads."""

    forbidden: set[str] = {
        str(Path(str(plan["source_receipt"]["pdf_path"])).resolve()),
        str((run.workdir.parents[3] / "benchmark_plan.json").resolve()),
    }
    for other in all_runs:
        if other == run:
            continue
        forbidden.add(str(other.workdir.resolve()))
        forbidden.add(str(other.task_root.resolve()))
    if run.treatment == "fiscalprompt":
        skill = Path(str(plan["candidate_identity"]["skill_path"])).resolve()
        forbidden.add(str(skill))
        forbidden.add(str(skill.parents[2]))
    tool_inputs = [str(value) for value in metrics.get("tool_inputs", [])]
    violations = sorted(
        candidate
        for candidate in forbidden
        if any(candidate.casefold() in value.casefold() for value in tool_inputs)
    )
    if run.treatment == "fiscalprompt" and any(
        PROMPT_OPTIMIZER_PATH_COMPONENT.search(value) for value in tool_inputs
    ):
        violations.append("prompt_optimizer_skill_reference")
    if run.treatment == "optimize_prompt" and any(
        _tool_query_mentions_fiscalprompt(value) for value in tool_inputs
    ):
        violations.append("fiscalprompt_search_query")
    traversal = any(
        ".." in Path(token).parts
        for value in tool_inputs
        for token in re.findall(r"[^\s'\";,]+", value)
    )
    if traversal:
        violations.append("relative_parent_traversal")
    return {"status": "pass" if not violations else "fail", "violations": violations}


def _tool_query_mentions_fiscalprompt(tool_input: str) -> bool:
    """Return whether a recorded search query targets FiscalPrompt."""

    try:
        payload = json.loads(tool_input)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, Mapping):
        return False
    queries: list[str] = []
    query = payload.get("query")
    if isinstance(query, str):
        queries.append(query)
    action = payload.get("action")
    if isinstance(action, Mapping):
        action_queries = action.get("queries")
        if isinstance(action_queries, Sequence) and not isinstance(
            action_queries, (str, bytes)
        ):
            queries.extend(value for value in action_queries if isinstance(value, str))
    return any("fiscalprompt" in value.casefold() for value in queries)


def _fact_anchor_checks(run: PreparedRun, case: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for artifact_name, filename in (
        ("prompt", "prompt_used.md"),
        ("answer", "answer.md"),
    ):
        path = run.workdir / "result" / filename
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        presence = {
            anchor: anchor.casefold() in text.casefold()
            for anchor in case["fact_anchors"]
        }
        result[artifact_name] = {
            "anchors": presence,
            "all_present": all(presence.values()),
        }
    return result


def build_review_packets(
    suite: Mapping[str, Any],
    *,
    output_root: Path,
    run_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Create blinded A/B packets; semantic scoring remains reviewer-owned."""

    validated = validate_suite(suite)
    case_index = {str(case["id"]): case for case in validated["cases"]}
    run_index = {
        (str(run["case_id"]), int(run["repeat"]), str(run["treatment"])): run
        for run in run_records
    }
    mappings: list[dict[str, Any]] = []
    packet_root = output_root / "review_packets"
    for case_id, case in case_index.items():
        for repeat in range(1, int(validated["repeats"]) + 1):
            pair = {
                treatment: run_index[(case_id, repeat, treatment)]
                for treatment in TREATMENTS
            }
            labels = ["A", "B"]
            secrets.SystemRandom().shuffle(labels)
            treatment_by_label = dict(zip(labels, TREATMENTS, strict=True))
            packet_id = f"{case_id}-repeat-{repeat:02d}"
            packet = packet_root / packet_id
            packet.mkdir(parents=True)
            _write_json(packet / "case.json", _public_case(case))
            artifacts: dict[str, dict[str, str]] = {}
            for label in ("A", "B"):
                treatment = treatment_by_label[label]
                run = pair[treatment]
                answer = Path(str(run["artifacts"]["answer"]["path"]))
                prompt = Path(str(run["artifacts"]["prompt"]["path"]))
                if not answer.is_file() or not prompt.is_file():
                    raise ValueError(f"missing artifacts for review packet {packet_id}")
                answer_target = packet / f"answer_{label}.md"
                prompt_target = packet / f"prompt_{label}.md"
                shutil.copy2(answer, answer_target)
                shutil.copy2(prompt, prompt_target)
                artifacts[label] = {
                    "answer_sha256": _sha256_file(answer_target),
                    "prompt_sha256": _sha256_file(prompt_target),
                }
            review_instructions = _review_instructions(suite, packet_id, artifacts)
            (packet / "review_instructions.md").write_text(
                review_instructions, encoding="utf-8"
            )
            review_template = _review_template(suite, packet_id, artifacts)
            _write_json(packet / "review_template.json", review_template)
            (packet / "reviews").mkdir()
            mapping = {
                "packet_id": packet_id,
                "case_id": case_id,
                "repeat": repeat,
                "treatment_by_label": treatment_by_label,
                "artifacts": artifacts,
                "review_instructions_sha256": _sha256_file(
                    packet / "review_instructions.md"
                ),
                "builder_thread_ids": {
                    treatment: str(pair[treatment]["metrics"]["thread_id"])
                    for treatment in TREATMENTS
                },
            }
            if not all(mapping["builder_thread_ids"].values()):
                raise ValueError(f"missing builder thread ID for packet {packet_id}")
            mappings.append(mapping)
    return mappings


def _review_instructions(
    suite: Mapping[str, Any], packet_id: str, artifacts: Mapping[str, Any]
) -> str:
    rubric = _mapping(suite["rubric"], label="rubric")
    lines = [
        "# Independent blinded review",
        "",
        f"Packet: `{packet_id}`",
        "",
        "Review A and B without guessing or recording which system produced them.",
        "Score each declared dimension from 1 (unacceptable) to 5 (excellent).",
        "Tax correctness and professional judgment must be assessed semantically; do not",
        "replace them with keyword counts. Record any hard failure with concrete evidence.",
        "Use a fresh reviewer thread that did not build either answer.",
        "",
        "## Prompt dimensions",
    ]
    for dimension in _sequence(rubric["prompt_dimensions"], label="prompt_dimensions"):
        item = _mapping(dimension, label="prompt dimension")
        lines.append(f"- `{item['id']}`: {item['description']}")
    lines.extend(["", "## Answer dimensions"])
    for dimension in _sequence(rubric["answer_dimensions"], label="answer_dimensions"):
        item = _mapping(dimension, label="answer dimension")
        lines.append(f"- `{item['id']}`: {item['description']}")
    lines.extend(
        [
            "",
            "## Hard failures",
            *[
                f"- `{failure}`"
                for failure in _sequence(rubric["hard_failures"], label="hard_failures")
            ],
            "",
            "Copy `review_template.json` into `reviews/`, complete it without changing",
            "the packet or artifact hashes, and retain A/B labels.",
            "",
            f"A hashes: `{json.dumps(artifacts['A'], sort_keys=True)}`",
            f"B hashes: `{json.dumps(artifacts['B'], sort_keys=True)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _review_template(
    suite: Mapping[str, Any], packet_id: str, artifacts: Mapping[str, Any]
) -> dict[str, Any]:
    validated = validate_suite(suite)
    return {
        "schema_version": REVIEW_SCHEMA,
        "packet_id": packet_id,
        "reviewer": {
            "type": "REPLACE_WITH_model_OR_tax_professional",
            "id": "REPLACE_WITH_REVIEWER_ID",
            "model": None,
            "thread_id": "REPLACE_WITH_FRESH_THREAD_ID",
        },
        "artifact_hashes": artifacts,
        "scores": {
            label: {
                "prompt": {
                    dimension: 0
                    for dimension in validated["rubric_dimensions"]["prompt"]
                },
                "answer": {
                    dimension: 0
                    for dimension in validated["rubric_dimensions"]["answer"]
                },
            }
            for label in ("A", "B")
        },
        "hard_failures": {"A": [], "B": []},
        "pairwise_winner": {
            "prompt": "REPLACE_WITH_A_B_OR_tie",
            "answer": "REPLACE_WITH_A_B_OR_tie",
        },
        "rationale": {"A": "", "B": "", "comparison": ""},
    }


def run_prepared_benchmark(
    suite: Mapping[str, Any],
    *,
    output_root: Path,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    """Execute fresh treatment pairs and create blinded review packets."""

    validated = validate_suite(suite)
    prepared = _load_prepared(output_root, suite)
    if (output_root / "benchmark_runs.json").exists():
        raise FileExistsError("benchmark_runs.json already exists")
    case_index = {str(case["id"]): case for case in validated["cases"]}
    prepared_index = {(run.case_id, run.repeat, run.treatment): run for run in prepared}
    plan = _mapping(
        json.loads((output_root / "benchmark_plan.json").read_text(encoding="utf-8")),
        label="plan",
    )
    launch_order = plan["launch_order"]
    execution_records: list[dict[str, Any]] = []
    for pair_spec in _sequence(launch_order, label="launch_order"):
        pair = _mapping(pair_spec, label="launch_order[]")
        case_id = str(pair["case_id"])
        repeat = int(pair["repeat"])
        treatments = [str(value) for value in pair["treatments"]]
        runs = [
            prepared_index[(case_id, repeat, treatment)] for treatment in treatments
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _launch_run,
                    run,
                    codex_bin=codex_bin,
                    model=model,
                    reasoning_effort=reasoning_effort,
                )
                for run in runs
            ]
            execution_records.extend(future.result() for future in futures)

    run_records: list[dict[str, Any]] = []
    for execution in execution_records:
        run = execution["run"]
        artifacts = {
            "answer": _artifact_record(run, "answer.md"),
            "prompt": _artifact_record(run, "prompt_used.md"),
            "sources": _artifact_record(run, "sources.json"),
        }
        run_records.append(
            {
                "case_id": run.case_id,
                "repeat": run.repeat,
                "treatment": run.treatment,
                "process_exit_code": execution["process_exit_code"],
                "duration_ms": execution["duration_ms"],
                "started_at": execution["started_at"],
                "completed_at": execution["completed_at"],
                "execution_identity": {
                    "model": model,
                    "reasoning_effort": reasoning_effort,
                    "fresh_ephemeral_run": True,
                    "user_config_ignored": True,
                    "disabled_features": list(CODEX_DISABLED_FEATURES),
                },
                "metrics": execution["metrics"],
                "artifacts": artifacts,
                "mechanical_checks": {
                    "process_succeeded": execution["process_exit_code"] == 0,
                    "required_artifacts_exist": all(
                        artifact["exists"] for artifact in artifacts.values()
                    ),
                    "sources_json_valid": _sources_json_valid(
                        run.workdir / "result" / "sources.json"
                    ),
                    "treatment_isolation": _audit_treatment_isolation(
                        run,
                        metrics=execution["metrics"],
                        all_runs=prepared,
                        plan=plan,
                    ),
                    "fact_anchors": _fact_anchor_checks(run, case_index[run.case_id]),
                },
            }
        )
    mappings = build_review_packets(
        suite, output_root=output_root, run_records=run_records
    )
    payload = {
        "schema_version": RUNS_SCHEMA,
        "suite_id": validated["suite_id"],
        "recorded_at": _iso_now(),
        "producer": Path(__file__).name,
        "runs": run_records,
        "private_review_mappings": mappings,
        "review_status": "awaiting_independent_model_and_tax_professional_reviews",
    }
    _write_json(output_root / "benchmark_runs.json", payload)
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(value, label=str(path)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "evals"
        / "fiscalprompt_benchmark_suite.json",
    )
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--optimizer-skill",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "skills"
        / "prompt-optimizer"
        / "SKILL.md",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    suite = _load_json(args.suite)
    output_root = args.output_root.expanduser().resolve()
    if args.execute:
        if not output_root.is_dir():
            parser.error("prepare the output root before using --execute")
        run_prepared_benchmark(
            suite,
            output_root=output_root,
            codex_bin=args.codex_bin,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
        )
        LOGGER.info("Execution complete; blinded packets await independent review")
        return 0
    if args.pdf is None:
        parser.error("--pdf is required during preparation")
    prepare_benchmark(
        suite,
        pdf_path=args.pdf,
        output_root=output_root,
        optimizer_skill_path=args.optimizer_skill,
    )
    LOGGER.info("Plan prepared. Inspect benchmark_plan.json before paid execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
