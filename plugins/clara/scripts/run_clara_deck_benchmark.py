#!/usr/bin/env python3
"""Prepare or execute the sealed Clara HTML-versus-PPTX benchmark protocol."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import posixpath
import re
import secrets
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from summarize_html_deck_benchmark import validate_suite

__all__ = [
    "build_prompt",
    "parse_codex_jsonl",
    "perform_mechanical_checks",
    "prepare_benchmark",
    "verify_source_manifest",
    "verify_candidate_skill_identity",
]

LOGGER = logging.getLogger(__name__)
RUN_SCHEMA = "clara.html_deck_benchmark_runs.v1"
FORMAT_MARKER = "{{TARGET_FORMAT}}"
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
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PACKAGE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
PPTX_NS = {"p": PRESENTATION_NS, "a": DRAWING_NS}
EMU_PER_PIXEL = 9525


@dataclass(frozen=True)
class PreparedRun:
    """Immutable launch details for one format-specific benchmark run."""

    case_id: str
    mode: str
    output_format: str
    workdir: Path
    output_root: Path
    artifact_path: Path
    rendered_paths: tuple[Path, ...]
    prompt: str
    normalized_prompt: str
    source_manifest_sha256: str
    fixture_source: Path
    task_root: Path
    task_spec: Path
    task_manifest_sha256: str
    task_manifest_path: Path


def _task_tree_manifest(task_root: Path) -> tuple[str, tuple[dict[str, str], ...]]:
    """Fingerprint every directory and file in a sealed benchmark task tree."""

    root = task_root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"sealed task root is unavailable: {root}")
    records: list[dict[str, str]] = []
    rows: list[str] = []
    for path in sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    ):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError(f"sealed task tree contains a symlink: {relative}")
        if path.is_dir():
            records.append({"path": relative, "type": "directory"})
            rows.append(f"directory\0{relative}\n")
        elif path.is_file():
            digest = _sha256_file(path)
            records.append({"path": relative, "type": "file", "sha256": digest})
            rows.append(f"file\0{relative}\0{digest}\n")
        else:
            raise ValueError(
                f"sealed task tree contains an unsupported node: {relative}"
            )
    if not records:
        raise ValueError("sealed task tree must not be empty")
    return _sha256_bytes("".join(rows).encode("utf-8")), tuple(records)


def _seal_task_tree(task_root: Path) -> None:
    """Make task bytes read-only as a defense in depth before Codex launch."""

    root = task_root.expanduser().resolve()
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)


def _verify_prepared_task(prepared: PreparedRun) -> str:
    task_link = prepared.workdir / "task"
    if (
        not task_link.is_symlink()
        or task_link.resolve() != prepared.task_root.resolve()
    ):
        raise ValueError(
            f"sealed task link changed for {prepared.case_id}:{prepared.output_format}"
        )
    observed, _ = _task_tree_manifest(prepared.task_root)
    if observed != prepared.task_manifest_sha256:
        raise ValueError(
            f"sealed task tree changed for {prepared.case_id}:{prepared.output_format}"
        )
    return observed


def _json_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _directory_tree_sha256(
    root: Path, *, excluded_top_levels: frozenset[str] = frozenset()
) -> str:
    """Hash deterministic directory bytes while excluding transient caches."""

    tree_root = root.expanduser().resolve()
    if not tree_root.is_dir():
        raise ValueError(f"runtime tree root is unavailable: {tree_root}")
    rows: list[str] = []
    for path in sorted(
        tree_root.rglob("*"), key=lambda item: item.relative_to(tree_root).as_posix()
    ):
        relative = path.relative_to(tree_root)
        if (
            relative.parts[0] in excluded_top_levels
            or "__pycache__" in relative.parts
            or path.name in {".DS_Store"}
            or path.suffix in {".pyc", ".pyo"}
        ):
            continue
        if path.is_symlink():
            raise ValueError(f"plugin runtime tree contains a symlink: {relative}")
        if path.is_file():
            rows.append(f"{relative.as_posix()}\0{_sha256_file(path)}\n")
    if not rows:
        raise ValueError("plugin runtime tree must not be empty")
    return _sha256_bytes("".join(rows).encode("utf-8"))


def _plugin_runtime_tree_sha256(root: Path) -> str:
    """Hash Clara runtime bytes while excluding recursive benchmark evidence."""

    return _directory_tree_sha256(root, excluded_top_levels=frozenset({"evals"}))


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def verify_candidate_skill_identity(
    suite: Mapping[str, Any],
    *,
    installed_clara_root: Path | None = None,
    presentations_root: Path | None = None,
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Fail unless source and installed format skills match the sealed candidate."""

    expected = _json_mapping(
        suite.get("candidate_skill_identity"), label="candidate_skill_identity"
    )
    plugin_root = Path(__file__).resolve().parents[1]
    source_manifest = plugin_root / ".codex-plugin" / "plugin.json"
    source_plugin = json.loads(source_manifest.read_text(encoding="utf-8"))
    clara_expected = dict(_json_mapping(expected["clara"], label="identity clara"))
    if source_plugin.get("version") != clara_expected["version"]:
        raise ValueError("source Clara version does not match the benchmark suite")
    source_skill = plugin_root / "skills" / "html-deck" / "SKILL.md"
    if _sha256_file(source_skill) != clara_expected["skill_sha256"]:
        raise ValueError(
            "source Clara HTML skill hash does not match the benchmark suite"
        )
    if _sha256_file(source_manifest) != clara_expected["plugin_manifest_sha256"]:
        raise ValueError("source Clara plugin manifest hash does not match the suite")
    if (
        _plugin_runtime_tree_sha256(plugin_root)
        != clara_expected["runtime_tree_sha256"]
    ):
        raise ValueError("source Clara runtime tree does not match the benchmark suite")

    clara_root = installed_clara_root
    if clara_root is None:
        clara_root = (
            Path.home()
            / ".codex"
            / "plugins"
            / "cache"
            / "mp"
            / "clara"
            / str(clara_expected["version"])
        )
    clara_root = clara_root.expanduser().resolve()
    if clara_root.name != str(clara_expected["version"]):
        raise ValueError("installed Clara root does not match the sealed version")
    installed_manifest = clara_root / ".codex-plugin" / "plugin.json"
    installed_skill = clara_root / "skills" / "html-deck" / "SKILL.md"
    if not installed_manifest.is_file() or not installed_skill.is_file():
        raise ValueError(f"required Clara {clara_expected['version']} is not installed")
    if _sha256_file(installed_manifest) != clara_expected["plugin_manifest_sha256"]:
        raise ValueError(
            "installed Clara plugin manifest does not match source candidate"
        )
    if _sha256_file(installed_skill) != clara_expected["skill_sha256"]:
        raise ValueError("installed Clara HTML skill does not match source candidate")
    if _plugin_runtime_tree_sha256(clara_root) != clara_expected["runtime_tree_sha256"]:
        raise ValueError("installed Clara runtime tree does not match source candidate")

    presentations_expected = dict(
        _json_mapping(expected["presentations"], label="identity presentations")
    )
    presentation_skill_root = presentations_root
    if presentation_skill_root is None:
        presentation_skill_root = (
            Path.home()
            / ".codex"
            / "plugins"
            / "cache"
            / "openai-primary-runtime"
            / "presentations"
            / str(presentations_expected["version"])
            / "skills"
            / "presentations"
        )
    presentation_skill_root = presentation_skill_root.expanduser().resolve()
    if str(presentations_expected["version"]) not in presentation_skill_root.parts:
        raise ValueError(
            "installed Presentations root does not match the sealed runtime version"
        )
    presentation_skill = presentation_skill_root / "SKILL.md"
    if not presentation_skill.is_file():
        raise ValueError(
            f"required Presentations {presentations_expected['version']} is not installed"
        )
    if _sha256_file(presentation_skill) != presentations_expected["skill_sha256"]:
        raise ValueError("installed Presentations skill does not match the suite")
    if (
        _directory_tree_sha256(presentation_skill_root)
        != presentations_expected["skill_tree_sha256"]
    ):
        raise ValueError("installed Presentations skill tree does not match the suite")
    return (
        {
            "clara": {key: str(value) for key, value in clara_expected.items()},
            "presentations": {
                key: str(value) for key, value in presentations_expected.items()
            },
        },
        {
            "clara_root": str(clara_root),
            "presentations_root": str(presentation_skill_root),
        },
    )


def verify_source_manifest(case: Mapping[str, Any], fixture_root: Path) -> Path:
    """Verify every sealed source byte and return the resolved fixture directory."""

    fixture = (fixture_root / str(case["fixture_subdirectory"])).resolve()
    manifest = _json_mapping(
        case.get("source_manifest"), label=f"case {case.get('id')} source_manifest"
    )
    files = manifest.get("files")
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes, bytearray)):
        raise ValueError("source_manifest.files must be a list")
    rows: list[str] = []
    for raw_item in files:
        item = _json_mapping(raw_item, label="source manifest item")
        relative = Path(str(item["path"]))
        path = (fixture / relative).resolve()
        if not path.is_relative_to(fixture):
            raise ValueError(f"manifest path escapes fixture root: {relative}")
        if not path.is_file():
            raise ValueError(f"sealed fixture file is missing: {path}")
        observed = _sha256_file(path)
        expected = str(item["sha256"])
        if observed != expected:
            raise ValueError(
                f"sealed fixture hash mismatch for {relative}: expected {expected}, got {observed}"
            )
        rows.append(f"{relative.as_posix()}\0{observed}\n")
    manifest_hash = _sha256_bytes("".join(sorted(rows)).encode("utf-8"))
    if manifest_hash != manifest.get("manifest_sha256"):
        raise ValueError(f"sealed fixture manifest fingerprint mismatch for {fixture}")
    return fixture


def verify_baseline_evidence(case: Mapping[str, Any], fixture: Path) -> str:
    """Verify preserved historical summaries/artifacts without copying them to runs."""

    manifest = _json_mapping(
        case.get("baseline_evidence"), label=f"case {case.get('id')} baseline_evidence"
    )
    rows: list[str] = []
    for raw_item in manifest["files"]:
        item = _json_mapping(raw_item, label="baseline evidence item")
        relative = Path(str(item["path"]))
        path = (fixture / relative).resolve()
        if not path.is_relative_to(fixture) or not path.is_file():
            raise ValueError(f"baseline evidence file is unavailable: {relative}")
        observed = _sha256_file(path)
        if observed != item["sha256"]:
            raise ValueError(f"baseline evidence hash mismatch for {relative}")
        rows.append(f"{relative.as_posix()}\0{observed}\n")
    observed_manifest = _sha256_bytes("".join(sorted(rows)).encode("utf-8"))
    if observed_manifest != manifest["manifest_sha256"]:
        raise ValueError("baseline evidence manifest fingerprint mismatch")
    return observed_manifest


def _rewrite_task_spec(
    case: Mapping[str, Any],
    *,
    fixture_source: Path,
    workdir: Path,
    output_format: str,
    task_root: Path | None = None,
) -> Path:
    spec_relative = Path(str(case["spec_file"]))
    source_spec = fixture_source / spec_relative
    task_root = task_root or workdir / "task"
    task_root.mkdir(parents=True, exist_ok=True)
    task_spec = task_root / source_spec.name
    spec = json.loads(source_spec.read_text(encoding="utf-8"))
    if case["mode"] == "revise":
        baselines = _json_mapping(spec.get("baselines"), label="revision baselines")
        baseline = dict(
            _json_mapping(
                baselines.get(output_format), label=f"baseline {output_format}"
            )
        )
        baseline_root = task_root / "baseline"
        baseline_root.mkdir(parents=True, exist_ok=True)
        baseline["root"] = str(baseline_root.resolve())
        spec["baselines"] = {output_format: baseline}
    targets = _json_mapping(spec.get("target_outputs"), label="target_outputs")
    target = dict(
        _json_mapping(
            targets.get(output_format), label=f"target_outputs.{output_format}"
        )
    )
    target["root"] = str((workdir / "output").resolve())
    spec["target_outputs"] = {output_format: target}
    task_spec.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    instruction_source = fixture_source / str(case["instruction_file"])
    shutil.copy2(instruction_source, task_root / instruction_source.name)
    amendment_root = fixture_source / "common"
    for amendment in sorted(amendment_root.glob("protocol_amendment_*.json")):
        shutil.copy2(amendment, task_root / amendment.name)
    manifest = _json_mapping(case["source_manifest"], label="source_manifest")
    for raw_item in manifest["files"]:
        item = _json_mapping(raw_item, label="source manifest item")
        relative = Path(str(item["path"]))
        if relative.parts[:2] == ("common", "assets"):
            target_asset = task_root.joinpath(*relative.parts[1:])
            target_asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture_source / relative, target_asset)
        baseline_prefix = f"{output_format.lower()}_input"
        if case["mode"] == "revise" and relative.parts[0] == baseline_prefix:
            baseline_target = task_root / "baseline" / Path(*relative.parts[1:])
            baseline_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture_source / relative, baseline_target)
    return task_spec


def build_prompt(
    *,
    output_format: str,
    instruction_path: Path,
    spec_path: Path,
) -> tuple[str, str]:
    """Build paired prompts whose only varying text is TARGET_FORMAT."""

    template = f"""TARGET_FORMAT: {FORMAT_MARKER}

Execute the controlled deck benchmark defined in:
{instruction_path.as_posix()}
and
{spec_path.as_posix()}

Follow those sealed instructions exactly. This is a fresh ephemeral run. Do not inspect any prior run, the other format's baseline or output, or the external fixture from which this sealed copy was made. Do not use the web.

Apply any protocol_amendment_*.json files beside the rewritten specification in numeric order; the last amendment supersedes earlier conflicting geometry.

Use the installed format-specific skill. For HTML, use clara:html-deck but preserve the linked static packaging required by the sealed specification; the benchmark uses Clara's explicit static-deck compatibility QA profile rather than requiring Clara-native HUD, notes, ledger, or standalone packaging. For PPTX, use presentations:Presentations. Write only to the target root in the rewritten specification. Independent benchmark code will calculate artifact hashes and mechanical checks; a run_report self-assessment is not accepted as benchmark evidence.
"""
    normalized = template
    prompt = template.replace(FORMAT_MARKER, output_format)
    return prompt, normalized


def _target_paths(
    case: Mapping[str, Any], task_spec: Path, output_format: str
) -> tuple[Path, Path, tuple[Path, ...]]:
    spec = json.loads(task_spec.read_text(encoding="utf-8"))
    target = _json_mapping(
        _json_mapping(spec["target_outputs"], label="target_outputs")[output_format],
        label=f"target_outputs.{output_format}",
    )
    output_root = Path(str(target["root"])).resolve()
    artifact = output_root / str(target["artifact"])
    rendered = tuple(output_root / str(path) for path in target["rendered_slides"])
    return output_root, artifact, rendered


def prepare_benchmark(
    suite: Mapping[str, Any],
    *,
    fixture_root: Path,
    output_root: Path,
) -> list[PreparedRun]:
    """Verify inputs and build isolated paired workspaces without launching Codex."""

    suite_data = validate_suite(suite)
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    prepared: list[PreparedRun] = []
    baseline_evidence_manifests: dict[str, str] = {}
    for case in suite_data["cases"]:
        fixture_source = verify_source_manifest(case, fixture_root)
        baseline_evidence_manifests[str(case["id"])] = verify_baseline_evidence(
            case, fixture_source
        )
        case_root = output_root / str(case["id"])
        for output_format in ("HTML", "PPTX"):
            workdir = case_root / "runs" / output_format.lower()
            workdir.mkdir(parents=True, exist_ok=False)
            task_root = case_root / "sealed_tasks" / output_format.lower()
            task_spec = _rewrite_task_spec(
                case,
                fixture_source=fixture_source,
                workdir=workdir,
                output_format=output_format,
                task_root=task_root,
            )
            output_path, artifact, rendered = _target_paths(
                case, task_spec, output_format
            )
            output_path.mkdir(parents=True, exist_ok=True)
            task_manifest_sha256, task_manifest_records = _task_tree_manifest(task_root)
            manifest_root = case_root / "sealed_task_manifests"
            manifest_root.mkdir(parents=True, exist_ok=True)
            task_manifest_path = manifest_root / f"{output_format.lower()}.json"
            task_manifest_path.write_text(
                json.dumps(
                    {
                        "algorithm": "sha256",
                        "manifest_sha256": task_manifest_sha256,
                        "task_root": str(task_root.resolve()),
                        "records": task_manifest_records,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            _seal_task_tree(task_root)
            (workdir / "task").symlink_to(task_root.resolve(), target_is_directory=True)
            prompt, normalized = build_prompt(
                output_format=output_format,
                instruction_path=Path("task")
                / Path(str(case["instruction_file"])).name,
                spec_path=Path("task") / task_spec.name,
            )
            prepared.append(
                PreparedRun(
                    case_id=str(case["id"]),
                    mode=str(case["mode"]),
                    output_format=output_format,
                    workdir=workdir.resolve(),
                    output_root=output_path,
                    artifact_path=artifact,
                    rendered_paths=rendered,
                    prompt=prompt,
                    normalized_prompt=normalized,
                    source_manifest_sha256=str(
                        _json_mapping(case["source_manifest"], label="source_manifest")[
                            "manifest_sha256"
                        ]
                    ),
                    fixture_source=fixture_source,
                    task_root=task_root.resolve(),
                    task_spec=task_spec,
                    task_manifest_sha256=task_manifest_sha256,
                    task_manifest_path=task_manifest_path.resolve(),
                )
            )
    plan = {
        "schema_version": "clara.html_deck_benchmark_plan.v1",
        "suite_id": suite["suite_id"],
        "suite_fingerprint_sha256": _canonical_sha256(suite),
        "created_at": _iso_now(),
        "baseline_evidence_manifests": baseline_evidence_manifests,
        "runs": [
            {
                "case_id": run.case_id,
                "format": run.output_format,
                "workdir": str(run.workdir),
                "output_root": str(run.output_root),
                "artifact_path": str(run.artifact_path),
                "prompt_sha256": _sha256_bytes(run.prompt.encode("utf-8")),
                "normalized_prompt_sha256": _sha256_bytes(
                    run.normalized_prompt.encode("utf-8")
                ),
                "source_manifest_sha256": run.source_manifest_sha256,
                "sealed_task_root": str(run.task_root),
                "sealed_task_manifest_sha256": run.task_manifest_sha256,
                "sealed_task_manifest_path": str(run.task_manifest_path),
            }
            for run in prepared
        ],
    }
    (output_root / "benchmark_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return prepared


def parse_codex_jsonl(payload: bytes) -> dict[str, Any]:
    """Extract usage, identity hints, thread ID, and tool commands from Codex JSONL."""

    events: list[Mapping[str, Any]] = []
    for line_number, raw_line in enumerate(payload.split(b"\n"), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid Codex JSONL at line {line_number}") from exc
        events.append(_json_mapping(event, label=f"Codex event {line_number}"))
    if not events:
        raise ValueError("Codex emitted no JSONL events")

    usage: Mapping[str, Any] | None = None
    thread_id = ""
    observed_models: set[str] = set()
    observed_efforts: set[str] = set()
    tool_ids: set[str] = set()
    commands: list[str] = []
    tool_inputs_by_id: dict[str, str] = {}
    for event in events:
        if isinstance(event.get("thread_id"), str):
            thread_id = str(event["thread_id"])
        event_usage = event.get("usage")
        if isinstance(event_usage, Mapping):
            usage = event_usage
        for model_key in ("model", "model_id"):
            if isinstance(event.get(model_key), str):
                observed_models.add(str(event[model_key]))
        for effort_key in ("reasoning_effort", "model_reasoning_effort"):
            if isinstance(event.get(effort_key), str):
                observed_efforts.add(str(event[effort_key]))
        item = event.get("item")
        if isinstance(item, Mapping):
            item_type = str(item.get("type", ""))
            if item_type in TOOL_ITEM_TYPES:
                item_id = str(item.get("id") or f"event-{len(tool_ids) + 1}")
                tool_ids.add(item_id)
                invocation = {
                    key: item[key] for key in TOOL_INVOCATION_FIELDS if key in item
                }
                if invocation and item_id not in tool_inputs_by_id:
                    tool_inputs_by_id[item_id] = json.dumps(
                        invocation, ensure_ascii=False, sort_keys=True
                    )
            if item_type in {"command_execution", "mcp_tool_call"}:
                command = (
                    item.get("command") or item.get("arguments") or item.get("input")
                )
                if isinstance(command, str):
                    commands.append(command)
                elif isinstance(command, Mapping):
                    commands.append(json.dumps(command, sort_keys=True))
    if usage is None:
        raise ValueError("Codex JSONL contains no usage record")
    input_tokens = usage.get("input_tokens")
    cached_input_tokens = usage.get("cached_input_tokens", 0)
    output_tokens = usage.get("output_tokens")
    for name, value, allow_zero in (
        ("input_tokens", input_tokens, False),
        ("cached_input_tokens", cached_input_tokens, True),
        ("output_tokens", output_tokens, False),
    ):
        if type(value) is not int or value < (0 if allow_zero else 1):
            raise ValueError(f"Codex usage.{name} must be an integer")
    return {
        "thread_id": thread_id,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "tool_calls": len(tool_ids),
        "commands": commands,
        "tool_inputs": list(tool_inputs_by_id.values()),
        "observed_models": sorted(observed_models),
        "observed_reasoning_efforts": sorted(observed_efforts),
    }


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG file: {path}")
    return struct.unpack(">II", header[16:24])


def _html_text_and_slide_count(path: Path) -> tuple[str, int, list[str]]:
    source = path.read_text(encoding="utf-8")
    slide_pattern = re.compile(
        r"<section\b(?=[^>]*\bclass\s*=\s*(['\"])[^'\"]*\bslide\b[^'\"]*\1)[^>]*>",
        re.IGNORECASE,
    )
    matches = list(slide_pattern.finditer(source))
    visible_text = html.unescape(re.sub(r"<[^>]+>", " ", source))
    visible_text = re.sub(r"\s+", " ", visible_text).strip()
    slide_sources: list[str] = []
    for position, match in enumerate(matches):
        end = (
            matches[position + 1].start()
            if position + 1 < len(matches)
            else len(source)
        )
        slide_sources.append(source[match.start() : end])
    return visible_text, len(matches), slide_sources


class _VisibleSlideParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.slides: list[dict[str, Any]] = []
        self._slide_depth = 0
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "section" and "slide" in classes and self._slide_depth == 0:
            self.slides.append({"nodes": [], "images": []})
            self._slide_depth = 1
            return
        if self._slide_depth:
            if tag not in {
                "area",
                "base",
                "br",
                "col",
                "embed",
                "hr",
                "img",
                "input",
                "link",
                "meta",
                "source",
                "track",
                "wbr",
            }:
                self._slide_depth += 1
            if tag in {"script", "style"} or "speaker-notes" in classes:
                self._ignored_depth += 1
            if tag == "img" and values.get("src"):
                self.slides[-1]["images"].append(values["src"])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if not self._slide_depth:
            return
        if self._ignored_depth and tag in {"script", "style", "aside", "div"}:
            self._ignored_depth -= 1
        self._slide_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._slide_depth and not self._ignored_depth:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.slides[-1]["nodes"].append(value)


def _visible_slide_nodes(path: Path, output_format: str) -> list[list[str]]:
    if output_format == "HTML":
        parser = _VisibleSlideParser()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        return [list(slide["nodes"]) for slide in parser.slides]
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=lambda name: int(re.search(r"\d+", Path(name).stem).group()),
        )
        return [
            [
                html.unescape(value)
                for value in re.findall(
                    r"<a:t(?:\s[^>]*)?>(.*?)</a:t>",
                    archive.read(name).decode("utf-8"),
                    flags=re.DOTALL,
                )
            ]
            for name in slide_names
        ]


def _copy_tokens(nodes: Sequence[str]) -> Counter[str]:
    return Counter(
        token.casefold()
        for token in re.findall(r"[\w$%+.-]+", " ".join(nodes), flags=re.UNICODE)
    )


def _pptx_text_and_slide_count(path: Path) -> tuple[str, int, list[str]]:
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=lambda name: int(re.search(r"\d+", Path(name).stem).group()),
        )
        slide_texts: list[str] = []
        for name in slide_names:
            source = archive.read(name).decode("utf-8")
            parts = [
                html.unescape(value)
                for value in re.findall(
                    r"<a:t(?:\s[^>]*)?>(.*?)</a:t>", source, flags=re.DOTALL
                )
            ]
            slide_texts.append(" ".join(parts))
    return " ".join(slide_texts), len(slide_names), slide_texts


def _source_asset_hashes(path: Path, output_format: str) -> set[str]:
    if output_format == "HTML":
        asset_root = path.parent / "assets"
        return {
            _sha256_file(item) for item in asset_root.glob("*.png") if item.is_file()
        }
    with zipfile.ZipFile(path) as archive:
        return {
            _sha256_bytes(archive.read(name))
            for name in archive.namelist()
            if name.startswith("ppt/media/")
        }


def _expected_asset_hashes(case: Mapping[str, Any]) -> set[str]:
    manifest = _json_mapping(case["source_manifest"], label="source_manifest")
    return {
        str(item["sha256"])
        for item in manifest["files"]
        if str(item["path"]).lower().endswith(".png")
    }


def _create_expected_copy(spec: Mapping[str, Any]) -> list[str]:
    expected: list[str] = []
    for raw_slide in spec["slides"]:
        slide = _json_mapping(raw_slide, label="slide")
        for key in (
            "eyebrow",
            "brand",
            "title",
            "chart_caption_left",
            "chart_caption_right",
            "narrative_headline",
            "note",
            "footer",
        ):
            expected.append(str(slide[key]))
        for raw_kpi in slide["kpis"]:
            kpi = _json_mapping(raw_kpi, label="kpi")
            expected.extend((str(kpi["label"]), str(kpi["value"])))
    return expected


def _create_expected_slide_nodes(spec: Mapping[str, Any]) -> list[list[str]]:
    expected: list[list[str]] = []
    for raw_slide in spec["slides"]:
        slide = _json_mapping(raw_slide, label="slide")
        nodes = [
            str(slide["eyebrow"]),
            str(slide["brand"]),
            str(slide["title"]),
            str(slide["chart_caption_left"]),
            str(slide["chart_caption_right"]),
            str(slide["narrative_headline"]),
        ]
        for raw_kpi in slide["kpis"]:
            kpi = _json_mapping(raw_kpi, label="kpi")
            nodes.extend((str(kpi["label"]), str(kpi["value"])))
        nodes.extend((str(slide["note"]), str(slide["footer"]), str(slide["number"])))
        expected.append(nodes)
    return expected


def _revision_expected_slide_nodes(
    spec: Mapping[str, Any], output_format: str
) -> list[list[str]]:
    baseline = _json_mapping(spec["baselines"][output_format], label="baseline")
    baseline_path = Path(str(baseline["root"])) / str(baseline["artifact"])
    baseline_nodes = _visible_slide_nodes(baseline_path, output_format)
    if len(baseline_nodes) != 2:
        return []
    packet = _json_mapping(spec["revision_packet"], label="revision_packet")
    replacements = {
        str(item["from"]): str(item["to"]) for item in packet["copy_replacements"]
    }
    replacements[str(packet["global_style"]["brand_from"])] = str(
        packet["global_style"]["brand_to"]
    )
    ordered = [list(baseline_nodes[1]), list(baseline_nodes[0])]
    eyebrows = [
        str(packet["renumbering"]["output_slide_1_eyebrow"]),
        str(packet["renumbering"]["output_slide_2_eyebrow"]),
    ]
    pages = [
        str(packet["renumbering"]["output_slide_1_page_number"]),
        str(packet["renumbering"]["output_slide_2_page_number"]),
    ]
    for index, nodes in enumerate(ordered):
        transformed = [replacements.get(node, node) for node in nodes]
        transformed = [
            eyebrows[index] if node.startswith("EXHIBIT ") else node
            for node in transformed
        ]
        transformed = [
            pages[index] if node in {"1", "2"} else node for node in transformed
        ]
        ordered[index] = transformed
    return ordered


def _exact_visible_copy(
    path: Path, output_format: str, expected: Sequence[Sequence[str]]
) -> bool:
    observed = _visible_slide_nodes(path, output_format)
    return len(observed) == len(expected) and all(
        _copy_tokens(observed_nodes) == _copy_tokens(expected_nodes)
        for observed_nodes, expected_nodes in zip(observed, expected)
    )


def _slide_asset_hashes(path: Path, output_format: str) -> list[set[str]]:
    if output_format == "HTML":
        parser = _VisibleSlideParser()
        parser.feed(path.read_text(encoding="utf-8"))
        parser.close()
        result: list[set[str]] = []
        for slide in parser.slides:
            hashes = set()
            for value in slide["images"]:
                parsed = Path(str(value).split("?", 1)[0].split("#", 1)[0])
                candidate = (path.parent / parsed).resolve()
                if candidate.is_file() and candidate.is_relative_to(
                    path.parent.resolve()
                ):
                    hashes.add(_sha256_file(candidate))
            result.append(hashes)
        return result
    with zipfile.ZipFile(path) as archive:
        result = []
        slide_names = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=lambda name: int(re.search(r"\d+", Path(name).stem).group()),
        )
        for slide_name in slide_names:
            relation_name = f"ppt/slides/_rels/{Path(slide_name).name}.rels"
            hashes = set()
            if relation_name in archive.namelist():
                relations = ElementTree.fromstring(archive.read(relation_name))
                for relationship in relations.findall(
                    f"{{{PACKAGE_RELATIONSHIP_NS}}}Relationship"
                ):
                    if (
                        not relationship.get("Type", "").endswith("/image")
                        or relationship.get("TargetMode") == "External"
                    ):
                        continue
                    target = relationship.get("Target", "")
                    media_name = (
                        posixpath.normpath(target.lstrip("/"))
                        if target.startswith("/")
                        else posixpath.normpath(
                            posixpath.join(posixpath.dirname(slide_name), target)
                        )
                    )
                    if media_name == ".." or media_name.startswith("../"):
                        continue
                    if media_name in archive.namelist():
                        hashes.add(_sha256_bytes(archive.read(media_name)))
            result.append(hashes)
        return result


def _expected_slide_asset_hashes(
    case: Mapping[str, Any], spec: Mapping[str, Any]
) -> list[str]:
    manifest = _json_mapping(case["source_manifest"], label="source_manifest")
    by_name = {
        Path(str(item["path"])).name: str(item["sha256"])
        for item in manifest["files"]
        if str(item["path"]).lower().endswith(".png")
    }
    if case["mode"] == "create":
        return [
            by_name[Path(str(slide["chart_asset"])).name] for slide in spec["slides"]
        ]
    return [by_name["slide-2-chart.png"], by_name["slide-1-chart.png"]]


def _revision_expected_copy(spec: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    packet = _json_mapping(spec["revision_packet"], label="revision_packet")
    required = [str(item["to"]) for item in packet["copy_replacements"]]
    prohibited = [str(item["from"]) for item in packet["copy_replacements"]]
    required.append(str(packet["global_style"]["brand_to"]))
    required.extend(str(value) for value in packet["renumbering"].values())
    return required, prohibited


def _artifact_text_runs(path: Path, output_format: str) -> list[str]:
    if output_format == "HTML":
        source = path.read_text(encoding="utf-8")
        raw_values = re.findall(r">([^<>]+)<", source)
    else:
        with zipfile.ZipFile(path) as archive:
            raw_values = []
            for name in archive.namelist():
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name):
                    source = archive.read(name).decode("utf-8")
                    raw_values.extend(
                        re.findall(
                            r"<a:t(?:\s[^>]*)?>(.*?)</a:t>",
                            source,
                            flags=re.DOTALL,
                        )
                    )
    return [
        re.sub(r"\s+", " ", html.unescape(value)).strip()
        for value in raw_values
        if re.sub(r"\s+", " ", html.unescape(value)).strip()
    ]


def _revision_preserved_copy(
    spec: Mapping[str, Any], output_format: str, output_text: str
) -> bool:
    baseline = _json_mapping(spec["baselines"][output_format], label="baseline")
    baseline_path = Path(str(baseline["root"])) / str(baseline["artifact"])
    packet = _json_mapping(spec["revision_packet"], label="revision_packet")
    excluded = {str(item["from"]) for item in packet["copy_replacements"]} | {
        str(packet["global_style"]["brand_from"])
    }
    preserved = {
        value
        for value in _artifact_text_runs(baseline_path, output_format)
        if len(value) >= 3
        and value not in excluded
        and not value.startswith("EXHIBIT ")
    }
    return bool(preserved) and all(value in output_text for value in preserved)


def _revision_order_is_correct(slide_texts: Sequence[str]) -> bool:
    if len(slide_texts) != 2:
        return False
    return (
        "Consumer leads 2014 sales, COGS and volume" in slide_texts[0]
        and "2014 sales growth was led by Consumer" in slide_texts[1]
    )


class _HTMLRevisionStructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.slides: list[list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = []
        self.resources: list[tuple[str, str]] = []
        self._slide_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = tuple(sorted(values.get("class", "").split()))
        if tag == "link" and values.get("href"):
            self.resources.append(("link", values["href"]))
        elif tag == "script" and values.get("src"):
            self.resources.append(("script", values["src"]))
        if tag == "section" and "slide" in classes and self._slide_depth == 0:
            self.slides.append([])
            self._slide_depth = 1
        elif self._slide_depth and tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "source",
            "track",
            "wbr",
        }:
            self._slide_depth += 1
        if self._slide_depth:
            ignored_values = {"id", "src", "alt", "aria-labelledby", "hidden"}
            attribute_names = tuple(
                sorted(key for key in values if key not in ignored_values)
            )
            self.slides[-1].append((tag, classes, attribute_names))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._slide_depth:
            self._slide_depth -= 1


def _html_revision_inventory(
    path: Path,
) -> tuple[
    list[list[tuple[str, tuple[str, ...], tuple[str, ...]]]],
    list[tuple[str, str]],
]:
    parser = _HTMLRevisionStructureParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.slides, parser.resources


def _css_declarations(path: Path) -> dict[str, dict[str, str]]:
    source = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    result: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", source):
        selector = re.sub(r"\s+", " ", selector).strip()
        declarations: dict[str, str] = {}
        for raw_declaration in body.split(";"):
            if ":" not in raw_declaration:
                continue
            property_name, value = raw_declaration.split(":", 1)
            declarations[property_name.strip().lower()] = (
                re.sub(r"\s+", " ", value).strip().lower()
            )
        if declarations:
            result[selector] = declarations
    return result


def _css_px(value: Any) -> str:
    return f"{int(value)}px"


def _apply_css_geometry(
    expected: dict[str, dict[str, str]], selector: str, geometry: Mapping[str, Any]
) -> bool:
    if selector not in expected:
        return False
    property_names = {"x": "left", "y": "top", "w": "width", "h": "height"}
    for source_name, property_name in property_names.items():
        if source_name in geometry:
            expected[selector][property_name] = _css_px(geometry[source_name])
    if "align" in geometry:
        expected[selector]["text-align"] = str(geometry["align"]).lower()
    return True


def _revision_amendment_paths(spec: Mapping[str, Any], output: Path) -> list[Path]:
    roots = [
        output.parent.parent / "task",
        output.parent.parent / "common",
    ]
    baselines = _json_mapping(spec.get("baselines", {}), label="revision baselines")
    for raw_baseline in baselines.values():
        baseline = _json_mapping(raw_baseline, label="revision baseline")
        baseline_root = Path(str(baseline["root"]))
        roots.extend((baseline_root.parent, baseline_root.parent / "common"))
    seen: set[Path] = set()
    for root in roots:
        resolved = root.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        amendments = sorted(resolved.glob("protocol_amendment_*.json"))
        if amendments:
            return amendments
    return []


def _html_revision_fidelity(spec: Mapping[str, Any], output: Path) -> bool:
    baseline = _json_mapping(spec["baselines"]["HTML"], label="HTML baseline")
    baseline_root = Path(str(baseline["root"]))
    baseline_html = baseline_root / str(baseline["artifact"])
    baseline_structures, baseline_resources = _html_revision_inventory(baseline_html)
    output_structures, output_resources = _html_revision_inventory(output)
    if (
        len(baseline_structures) != 2
        or output_structures != [baseline_structures[1], baseline_structures[0]]
        or output_resources != baseline_resources
    ):
        return False
    for resource_type, relative in baseline_resources:
        baseline_resource = (baseline_root / relative).resolve()
        output_resource = (output.parent / relative).resolve()
        if resource_type == "script" and (
            not baseline_resource.is_file()
            or not output_resource.is_file()
            or _sha256_file(output_resource) != _sha256_file(baseline_resource)
        ):
            return False

    baseline_css = baseline_root / "styles.css"
    output_css = output.parent / "styles.css"
    if not baseline_css.is_file() or not output_css.is_file():
        return False
    expected = _css_declarations(baseline_css)
    packet = _json_mapping(spec["revision_packet"], label="revision_packet")
    global_style = _json_mapping(packet["global_style"], label="global_style")
    expected.get(":root", {})["--background"] = str(
        global_style["canvas_background_to"]
    ).lower()
    expected.get(":root", {})["--chart-background"] = str(
        global_style["chart_frame_background"]
    ).lower()
    layout = _json_mapping(
        packet["global_layout_1280x720"], label="global_layout_1280x720"
    )
    selector_by_name = {
        "chart_caption_left": ".chart-caption-left",
        "chart_caption_right": ".chart-caption-right",
        "chart_frame": ".chart-frame",
        "narrative_accent_rule": ".narrative-accent-rule",
        "narrative_headline": ".narrative-headline",
        "note": ".note",
    }
    if not all(
        _apply_css_geometry(
            expected,
            selector_by_name[name],
            _json_mapping(layout[name], label=f"layout {name}"),
        )
        for name in selector_by_name
    ):
        return False
    kpi = _json_mapping(layout["kpi_block"], label="layout kpi_block")
    if not _apply_css_geometry(expected, ".kpi-block", kpi):
        return False
    expected[".kpi-block"]["height"] = _css_px(int(kpi["row_h"]) * 3)
    if ".kpi-row" not in expected:
        return False
    expected[".kpi-row"]["width"] = _css_px(kpi["w"])
    expected[".kpi-row"]["height"] = _css_px(kpi["row_h"])

    for amendment_path in _revision_amendment_paths(spec, output):
        amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
        override = _json_mapping(amendment.get("override", {}), label="amendment")
        if "brand" in override and not _apply_css_geometry(
            expected,
            ".brand",
            _json_mapping(override["brand"], label="brand amendment"),
        ):
            return False
    return _css_declarations(output_css) == expected


def _xml_without_text_or_geometry(element: ElementTree.Element) -> str:
    clone = ElementTree.fromstring(ElementTree.tostring(element))
    for text_node in clone.findall(f".//{{{DRAWING_NS}}}t"):
        text_node.text = ""
    for transform in list(clone.findall(f".//{{{DRAWING_NS}}}xfrm")):
        parent = next(
            (candidate for candidate in clone.iter() if transform in list(candidate)),
            None,
        )
        if parent is not None:
            parent.remove(transform)
    return ElementTree.tostring(clone, encoding="unicode")


def _shape_geometry(shape: ElementTree.Element) -> tuple[int, int, int, int] | None:
    transform = shape.find(f"./{{{PRESENTATION_NS}}}spPr/{{{DRAWING_NS}}}xfrm")
    if transform is None:
        return None
    offset = transform.find(f"./{{{DRAWING_NS}}}off")
    extent = transform.find(f"./{{{DRAWING_NS}}}ext")
    if offset is None or extent is None:
        return None
    return tuple(
        int(value)
        for value in (
            offset.get("x", "0"),
            offset.get("y", "0"),
            extent.get("cx", "0"),
            extent.get("cy", "0"),
        )
    )


def _pptx_slide_inventory(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            (
                name
                for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            ),
            key=lambda name: int(re.search(r"\d+", Path(name).stem).group()),
        )
        for slide_name in slide_names:
            root = ElementTree.fromstring(archive.read(slide_name))
            shapes: dict[str, dict[str, Any]] = {}
            for shape in root.findall(".//p:sp", PPTX_NS):
                non_visual = shape.find("./p:nvSpPr/p:cNvPr", PPTX_NS)
                if non_visual is None:
                    continue
                role = re.sub(r"^slide-\d+-", "", non_visual.get("name", ""))
                text_body = shape.find("./p:txBody", PPTX_NS)
                shape_properties = shape.find("./p:spPr", PPTX_NS)
                shapes[role] = {
                    "geometry": _shape_geometry(shape),
                    "style": (
                        _xml_without_text_or_geometry(text_body)
                        if text_body is not None
                        else ""
                    )
                    + (
                        _xml_without_text_or_geometry(shape_properties)
                        if shape_properties is not None
                        else ""
                    ),
                    "editable_text_runs": len(shape.findall(".//a:t", PPTX_NS)),
                }
            pictures = []
            for picture in root.findall(".//p:pic", PPTX_NS):
                properties = picture.find("./p:spPr", PPTX_NS)
                geometry = _shape_geometry(picture)
                if properties is not None:
                    transform = properties.find("./a:xfrm", PPTX_NS)
                    if transform is not None:
                        offset = transform.find("./a:off", PPTX_NS)
                        extent = transform.find("./a:ext", PPTX_NS)
                        if offset is not None and extent is not None:
                            geometry = tuple(
                                int(value)
                                for value in (
                                    offset.get("x", "0"),
                                    offset.get("y", "0"),
                                    extent.get("cx", "0"),
                                    extent.get("cy", "0"),
                                )
                            )
                pictures.append(
                    {
                        "geometry": geometry,
                        "no_change_aspect": picture.find(
                            ".//p:cNvPicPr/a:picLocks[@noChangeAspect='1']", PPTX_NS
                        )
                        is not None,
                        "cropped": picture.find(".//a:srcRect", PPTX_NS) is not None,
                    }
                )
            background = root.find("./p:cSld/p:bg//a:srgbClr", PPTX_NS)
            result.append(
                {
                    "shapes": shapes,
                    "pictures": pictures,
                    "background": (
                        background.get("val", "") if background is not None else ""
                    ),
                }
            )
    return result


def _emu_geometry(geometry: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return tuple(int(geometry[name]) * EMU_PER_PIXEL for name in ("x", "y", "w", "h"))


def _pptx_revision_fidelity(spec: Mapping[str, Any], output: Path) -> bool:
    baseline = _json_mapping(spec["baselines"]["PPTX"], label="PPTX baseline")
    baseline_path = Path(str(baseline["root"])) / str(baseline["artifact"])
    baseline_slides = _pptx_slide_inventory(baseline_path)
    output_slides = _pptx_slide_inventory(output)
    if len(baseline_slides) != 2 or len(output_slides) != 2:
        return False
    packet = _json_mapping(spec["revision_packet"], label="revision_packet")
    target_background = str(packet["global_style"]["canvas_background_to"])[1:].upper()
    layout = _json_mapping(
        packet["global_layout_1280x720"], label="global_layout_1280x720"
    )
    role_layout = {
        "chart-caption-left": layout["chart_caption_left"],
        "chart-caption-right": layout["chart_caption_right"],
        "chart-frame": layout["chart_frame"],
        "narrative-accent-rule": layout["narrative_accent_rule"],
        "narrative-headline": layout["narrative_headline"],
        "note": layout["note"],
    }
    for amendment_path in _revision_amendment_paths(spec, output):
        amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
        override = _json_mapping(amendment.get("override", {}), label="amendment")
        if "brand" in override:
            role_layout["brand"] = override["brand"]
    kpi = _json_mapping(layout["kpi_block"], label="kpi_block")
    for output_index, baseline_index in enumerate((1, 0)):
        observed = output_slides[output_index]
        source = baseline_slides[baseline_index]
        if (
            observed["background"] != target_background
            or set(observed["shapes"]) != set(source["shapes"])
            or len(observed["pictures"]) != 1
        ):
            return False
        for role, source_shape in source["shapes"].items():
            output_shape = observed["shapes"][role]
            if (
                output_shape["style"] != source_shape["style"]
                or output_shape["editable_text_runs"]
                != source_shape["editable_text_runs"]
            ):
                return False
            expected_geometry = source_shape["geometry"]
            if role in role_layout:
                expected_geometry = _emu_geometry(
                    _json_mapping(role_layout[role], label=f"layout {role}")
                )
            match = re.fullmatch(r"kpi-(\d+)-(label|value|separator)", role)
            if match:
                row = int(match.group(1)) - 1
                kind = match.group(2)
                x = int(kpi["x"])
                y = int(kpi["y"]) + row * int(kpi["row_h"])
                if kind == "label":
                    source_value = source["shapes"][f"kpi-{row + 1}-value"]["geometry"]
                    if source_value is None:
                        return False
                    value_x_px = source_value[0] // EMU_PER_PIXEL
                    expected_geometry = _emu_geometry(
                        {
                            "x": x,
                            "y": y,
                            "w": value_x_px - x,
                            "h": kpi["row_h"],
                        }
                    )
                elif kind == "separator":
                    expected_geometry = _emu_geometry(
                        {
                            "x": x,
                            "y": y + int(kpi["row_h"]),
                            "w": kpi["w"],
                            "h": 1,
                        }
                    )
            if output_shape["geometry"] != expected_geometry:
                return False
        frame = observed["shapes"]["chart-frame"]["geometry"]
        picture = observed["pictures"][0]
        picture_geometry = picture["geometry"]
        if (
            frame is None
            or picture_geometry is None
            or not picture["no_change_aspect"]
            or picture["cropped"]
        ):
            return False
        frame_x, frame_y, frame_w, frame_h = frame
        picture_x, picture_y, picture_w, picture_h = picture_geometry
        if (
            picture_x < frame_x
            or picture_y < frame_y
            or picture_x + picture_w > frame_x + frame_w
            or picture_y + picture_h > frame_y + frame_h
            or abs((picture_x - frame_x) - (frame_w - picture_w) / 2) > 1
            or abs((picture_y - frame_y) - (frame_h - picture_h) / 2) > 1
        ):
            return False
    return True


def _render_records(paths: Sequence[Path], *, renderer: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
        width, height = _png_dimensions(path)
        records.append(
            {
                "path": str(path.resolve()),
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
                "width": width,
                "height": height,
                "renderer": renderer,
            }
        )
    return records


def _render_set_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    payload = "".join(
        f"{index}\0{record['sha256']}\n"
        for index, record in enumerate(records, start=1)
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _run_html_validators(
    artifact: Path, audit_root: Path
) -> tuple[bool, bool, list[dict[str, Any]]]:
    skill_scripts = (
        Path(__file__).resolve().parents[1] / "skills" / "html-deck" / "scripts"
    )
    audit_root.mkdir(parents=True, exist_ok=True)
    static_report = audit_root / "static_validation.json"
    static = subprocess.run(
        [
            sys.executable,
            str(skill_scripts / "validate_html_deck.py"),
            str(artifact),
            "--report",
            str(static_report),
            "--profile",
            "static",
            "--allow-readable-path",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    browser = subprocess.run(
        [
            sys.executable,
            str(skill_scripts / "browser_qa_html_deck.py"),
            str(artifact),
            "--output-dir",
            str(audit_root / "browser"),
            "--profile",
            "static",
            "--viewport",
            "benchmark=1280x720",
            "--warnings-as-errors",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=300,
    )
    (audit_root / "static_validation.stderr.txt").write_text(
        static.stderr, encoding="utf-8"
    )
    (audit_root / "browser_qa.stderr.txt").write_text(browser.stderr, encoding="utf-8")
    browser_report_path = audit_root / "browser" / "browser-qa.json"
    screenshots: list[Path] = []
    if browser_report_path.is_file():
        browser_report = json.loads(browser_report_path.read_text(encoding="utf-8"))
        screenshots = [
            audit_root / "browser" / str(slide["screenshot"])
            for viewport in browser_report.get("viewports", [])
            for slide in viewport.get("slides", [])
            if slide.get("screenshot")
        ]
    return (
        static.returncode == 0,
        browser.returncode == 0,
        _render_records(screenshots, renderer="playwright-chromium"),
    )


def _find_pptx_renderer() -> Path:
    candidates = sorted(
        (
            Path.home()
            / ".codex"
            / "plugins"
            / "cache"
            / "openai-primary-runtime"
            / "presentations"
        ).glob("*/skills/presentations/container_tools/render_slides.py")
    )
    if not candidates:
        raise ValueError("Installed Presentations render_slides.py was not found")
    return candidates[-1].resolve()


def _render_pptx_independently(
    artifact: Path,
    audit_root: Path,
    *,
    renderer_path: Path | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    renderer = renderer_path.resolve() if renderer_path else _find_pptx_renderer()
    if not renderer.is_file():
        raise ValueError(f"Presentations renderer is unavailable: {renderer}")
    render_root = audit_root / "pptx-render"
    render_root.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(
        [
            sys.executable,
            str(renderer),
            str(artifact),
            "--output_dir",
            str(render_root),
            "--width",
            "1280",
            "--height",
            "720",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=300,
    )
    (audit_root / "pptx-render.stderr.txt").write_text(process.stderr, encoding="utf-8")
    paths = sorted(
        render_root.glob("slide-*.png"),
        key=lambda path: int(re.search(r"\d+", path.stem).group()),
    )
    records = _render_records(
        paths,
        renderer=f"presentations-render_slides:{_sha256_file(renderer)[:12]}",
    )
    return process.returncode == 0, records


def perform_mechanical_checks(
    prepared: PreparedRun,
    case: Mapping[str, Any],
    *,
    run_html_validators: bool = True,
    pptx_renderer: Path | None = None,
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Calculate artifact checks directly, without trusting an agent run report."""

    required = set(case["required_checks_by_format"][prepared.output_format])
    artifact_exists = prepared.artifact_path.is_file()
    checks = {name: False for name in required}
    checks["artifact_exists"] = artifact_exists
    checks["output_root_isolated"] = prepared.output_root.is_relative_to(
        prepared.workdir
    )
    if not artifact_exists:
        raise ValueError(f"benchmark artifact is missing: {prepared.artifact_path}")

    artifact_hash = _sha256_file(prepared.artifact_path)
    checks["artifact_hash_recorded"] = True
    if prepared.output_format == "HTML":
        text, slide_count, slide_texts = _html_text_and_slide_count(
            prepared.artifact_path
        )
    else:
        text, slide_count, slide_texts = _pptx_text_and_slide_count(
            prepared.artifact_path
        )
    spec = json.loads(prepared.task_spec.read_text(encoding="utf-8"))
    expected_slide_count = int(spec["experiment"]["slide_count"])
    checks["slide_count"] = slide_count == expected_slide_count
    if prepared.mode == "create":
        checks["exact_required_copy"] = _exact_visible_copy(
            prepared.artifact_path,
            prepared.output_format,
            _create_expected_slide_nodes(spec),
        )
    else:
        required_copy, prohibited_copy = _revision_expected_copy(spec)
        checks["exact_required_copy"] = (
            all(value in text for value in required_copy)
            and all(value not in text for value in prohibited_copy)
            and _exact_visible_copy(
                prepared.artifact_path,
                prepared.output_format,
                _revision_expected_slide_nodes(spec, prepared.output_format),
            )
        )
        checks["revision_fidelity"] = (
            checks["exact_required_copy"]
            and (_revision_order_is_correct(slide_texts))
            and _revision_preserved_copy(spec, prepared.output_format, text)
            and (
                _html_revision_fidelity(spec, prepared.artifact_path)
                if prepared.output_format == "HTML"
                else _pptx_revision_fidelity(spec, prepared.artifact_path)
            )
        )
    observed_slide_assets = _slide_asset_hashes(
        prepared.artifact_path, prepared.output_format
    )
    expected_slide_assets = _expected_slide_asset_hashes(case, spec)
    checks["source_asset_hashes"] = len(observed_slide_assets) == len(
        expected_slide_assets
    ) and all(
        expected_hash in observed_hashes
        for expected_hash, observed_hashes in zip(
            expected_slide_assets, observed_slide_assets
        )
    )

    rendered_records: list[dict[str, Any]] = []
    render_ok = False
    audit_root = prepared.workdir / "benchmark_audits"
    if prepared.output_format == "HTML" and run_html_validators:
        static_ok, browser_ok, rendered_records = _run_html_validators(
            prepared.artifact_path, audit_root
        )
        checks["static_validation"] = static_ok
        checks["browser_qa"] = browser_ok
        render_ok = browser_ok
    elif prepared.output_format == "PPTX":
        render_ok, rendered_records = _render_pptx_independently(
            prepared.artifact_path,
            audit_root,
            renderer_path=pptx_renderer,
        )
    dimensions_ok = bool(rendered_records) and all(
        (record["width"], record["height"]) == (1280, 720)
        for record in rendered_records
    )
    checks["rendered_slide_count"] = len(rendered_records) == expected_slide_count
    checks["rendered_dimensions"] = dimensions_ok and checks["rendered_slide_count"]
    if prepared.output_format == "PPTX":
        checks["render_qa"] = (
            zipfile.is_zipfile(prepared.artifact_path)
            and render_ok
            and checks["rendered_slide_count"]
            and checks["rendered_dimensions"]
        )
    return checks, {
        "path": str(prepared.artifact_path),
        "sha256": artifact_hash,
        "bytes": prepared.artifact_path.stat().st_size,
        "rendered_slides": rendered_records,
        "render_set_sha256": _render_set_sha256(rendered_records),
    }


def _audit_commands(
    tool_inputs: Sequence[str], prepared: PreparedRun, other_runs: Sequence[PreparedRun]
) -> str:
    forbidden = {
        str(prepared.fixture_source.resolve()),
        *(str(run.fixture_source.resolve()) for run in other_runs),
        *(str(run.output_root.resolve()) for run in other_runs),
        *(str(run.workdir.resolve()) for run in other_runs),
        *(str(run.task_root.resolve()) for run in other_runs),
        *(str(run.task_manifest_path.resolve()) for run in other_runs),
    }
    return (
        "fail"
        if any(path in tool_input for tool_input in tool_inputs for path in forbidden)
        or any(
            ".." in Path(token).parts
            for tool_input in tool_inputs
            for token in re.findall(r"[^\s'\";,]+", tool_input)
        )
        else "pass"
    )


def _launch_run(
    prepared: PreparedRun,
    *,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    task_manifest_before = _verify_prepared_task(prepared)
    event_log = prepared.workdir / "codex_events.jsonl"
    stderr_log = prepared.workdir / "codex_stderr.txt"
    last_message = prepared.workdir / "codex_last_message.txt"
    command = [
        codex_bin,
        "exec",
        "--json",
        "--ephemeral",
        "--skip-git-repo-check",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--sandbox",
        "workspace-write",
        "--cd",
        str(prepared.workdir),
        "--output-last-message",
        str(last_message),
        "-",
    ]
    started_at = _iso_now()
    started = time.monotonic()
    process = subprocess.run(
        command,
        input=prepared.prompt.encode("utf-8"),
        capture_output=True,
        check=False,
        timeout=3600,
    )
    duration_ms = max(1, round((time.monotonic() - started) * 1000))
    completed_at = _iso_now()
    event_log.write_bytes(process.stdout)
    stderr_log.write_bytes(process.stderr)
    task_manifest_after = _verify_prepared_task(prepared)
    metrics = parse_codex_jsonl(process.stdout)
    return {
        "prepared": prepared,
        "process_exit_code": process.returncode,
        "duration_ms": duration_ms,
        "started_at": started_at,
        "completed_at": completed_at,
        "event_log": event_log,
        "task_manifest_before": task_manifest_before,
        "task_manifest_after": task_manifest_after,
        "metrics": metrics,
    }


def _execute_pair(
    pair: Sequence[PreparedRun],
    *,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
) -> list[dict[str, Any]]:
    if {run.output_format for run in pair} != {"HTML", "PPTX"}:
        raise ValueError("each concurrent pair must contain HTML and PPTX")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _launch_run,
                run,
                codex_bin=codex_bin,
                model=model,
                reasoning_effort=reasoning_effort,
            )
            for run in pair
        ]
        return [future.result() for future in futures]


def _semantic_review_template(
    suite_data: Mapping[str, Any],
    run_records: Sequence[Mapping[str, Any]],
    packet_mappings: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    baseline_index = suite_data["baseline_index"]
    templates: list[dict[str, Any]] = []
    mapping_by_key = {
        (str(mapping["case_id"]), str(mapping["format"])): mapping
        for mapping in packet_mappings
    }
    for run in run_records:
        key = (str(run["case_id"]), str(run["format"]))
        packet = mapping_by_key[key]
        for reviewer_type in suite_data["reviewer_types"]:
            templates.append(
                {
                    "case_id": key[0],
                    "format": key[1],
                    "reviewer": {
                        "type": reviewer_type,
                        "id": "REPLACE_WITH_BLINDED_REVIEWER_ID",
                        "model": (
                            "REPLACE_WITH_REVIEW_MODEL"
                            if reviewer_type == "model"
                            else None
                        ),
                        "thread_id": "REPLACE_WITH_REVIEWER_THREAD_ID",
                    },
                    "review_packet_id": packet["packet_id"],
                    "review_prompt_sha256": packet["prompt_sha256"],
                    "source_requirements_sha256": packet["source_requirements_sha256"],
                    "candidate_artifact_sha256": run["artifact"]["sha256"],
                    "baseline_artifact_sha256": baseline_index[key]["artifact_sha256"],
                    "candidate_render_set_sha256": run["artifact"]["render_set_sha256"],
                    "baseline_render_set_sha256": packet["baseline_render_set_sha256"],
                    "scores_by_label": {
                        label: {
                            dimension: {
                                "score": None,
                                "pass": None,
                                "rationale": "",
                            }
                            for dimension in suite_data["dimensions"]
                        }
                        for label in ("A", "B")
                    },
                    "overall_rationale": "",
                }
            )
    return templates


def _baseline_artifact_path(
    case: Mapping[str, Any], fixture: Path, output_format: str
) -> Path:
    evidence = _json_mapping(case["baseline_evidence"], label="baseline_evidence")
    suffix = ".html" if output_format == "HTML" else ".pptx"
    candidates = [
        fixture / str(item["path"])
        for item in evidence["files"]
        if str(item["path"]).startswith(f"{output_format.lower()}_output/")
        and str(item["path"]).endswith(suffix)
    ]
    if len(candidates) != 1:
        raise ValueError(f"Expected one sealed {output_format} baseline artifact")
    return candidates[0].resolve()


def _render_baselines(
    suite_data: Mapping[str, Any],
    prepared: Sequence[PreparedRun],
    output_root: Path,
    *,
    pptx_renderer: Path,
) -> dict[tuple[str, str], dict[str, Any]]:
    fixture_by_case = {run.case_id: run.fixture_source for run in prepared}
    rendered: dict[tuple[str, str], dict[str, Any]] = {}
    for case in suite_data["cases"]:
        case_id = str(case["id"])
        for output_format in ("HTML", "PPTX"):
            artifact = _baseline_artifact_path(
                case, fixture_by_case[case_id], output_format
            )
            audit_root = (
                output_root / "baseline_audits" / case_id / output_format.lower()
            )
            if output_format == "HTML":
                static_ok, browser_ok, records = _run_html_validators(
                    artifact, audit_root
                )
                if not static_ok or not browser_ok:
                    raise ValueError(
                        f"Current renderer rejected sealed HTML baseline {case_id}"
                    )
            else:
                render_ok, records = _render_pptx_independently(
                    artifact, audit_root, renderer_path=pptx_renderer
                )
                if not render_ok:
                    raise ValueError(
                        f"Current renderer rejected sealed PPTX baseline {case_id}"
                    )
            if len(records) != 2:
                raise ValueError(
                    f"Baseline renderer did not produce two slides for {case_id}"
                )
            rendered[(case_id, output_format)] = {
                "artifact_path": str(artifact),
                "artifact_sha256": _sha256_file(artifact),
                "rendered_slides": records,
                "render_set_sha256": _render_set_sha256(records),
            }
    return rendered


def _create_review_packets(
    output_root: Path,
    run_records: Sequence[Mapping[str, Any]],
    baseline_renders: Mapping[tuple[str, str], Mapping[str, Any]],
    prepared_runs: Sequence[PreparedRun],
) -> list[dict[str, Any]]:
    prepared_by_key = {(run.case_id, run.output_format): run for run in prepared_runs}
    mappings: list[dict[str, Any]] = []
    for run in run_records:
        key = (str(run["case_id"]), str(run["format"]))
        baseline = baseline_renders[key]
        prepared = prepared_by_key[key]
        packet_id = secrets.token_hex(12)
        candidate_label = "A" if secrets.randbelow(2) == 0 else "B"
        baseline_label = "B" if candidate_label == "A" else "A"
        packet_root = output_root / "review_packets" / packet_id
        for label, records in (
            (candidate_label, run["artifact"]["rendered_slides"]),
            (baseline_label, baseline["rendered_slides"]),
        ):
            label_root = packet_root / label
            label_root.mkdir(parents=True, exist_ok=True)
            for index, record in enumerate(records, start=1):
                shutil.copy2(
                    Path(str(record["path"])), label_root / f"slide-{index}.png"
                )
        task_spec = json.loads(prepared.task_spec.read_text(encoding="utf-8"))
        task_spec.pop("baselines", None)
        task_spec.pop("target_outputs", None)
        instruction_candidates = sorted(prepared.task_spec.parent.glob("*.txt"))
        instruction_path = (
            instruction_candidates[0] if instruction_candidates else Path()
        )
        source_requirements = {
            "case_id": key[0],
            "task_brief": (
                instruction_path.read_text(encoding="utf-8")
                if instruction_path.is_file()
                else ""
            ),
            "requirements": task_spec,
            "protocol_amendments": [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted(
                    prepared.task_spec.parent.glob("protocol_amendment_*.json")
                )
            ],
        }
        requirements_path = packet_root / "source_requirements.json"
        requirements_path.write_text(
            json.dumps(source_requirements, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        source_assets = prepared.task_spec.parent / "assets"
        if source_assets.is_dir():
            shutil.copytree(source_assets, packet_root / "source_assets")
        prompt = (
            "Independently review render sets A and B without inferring their format history. "
            "Use source_requirements.json and any source_assets as the content authority. "
            "For source_fidelity, narrative_quality, visual_hierarchy, and decision_usefulness, "
            "score each label from 1 to 5, state pass/fail, compare non-regression, and give a concise rationale. "
            "Return your fresh reviewer thread ID. Do not inspect any builder run, mapping, or candidate_runs.json.\n"
        )
        prompt_path = packet_root / "review_prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        (packet_root / "response_template.json").write_text(
            json.dumps(
                {
                    "reviewer_thread_id": "",
                    "scores_by_label": {
                        label: {
                            dimension: {
                                "score": None,
                                "pass": None,
                                "rationale": "",
                            }
                            for dimension in (
                                "source_fidelity",
                                "narrative_quality",
                                "visual_hierarchy",
                                "decision_usefulness",
                            )
                        }
                        for label in ("A", "B")
                    },
                    "overall_rationale": "",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        mappings.append(
            {
                "packet_id": packet_id,
                "case_id": key[0],
                "format": key[1],
                "candidate_label": candidate_label,
                "baseline_label": baseline_label,
                "prompt_sha256": _sha256_file(prompt_path),
                "source_requirements_sha256": _sha256_file(requirements_path),
                "candidate_render_set_sha256": run["artifact"]["render_set_sha256"],
                "baseline_render_set_sha256": baseline["render_set_sha256"],
            }
        )
    return mappings


def execute_benchmark(
    suite: Mapping[str, Any],
    prepared: Sequence[PreparedRun],
    *,
    output_root: Path,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
    skill_identity: Mapping[str, Mapping[str, str]],
    skill_paths: Mapping[str, str],
) -> Path:
    """Launch each format pair concurrently and write runner-derived records."""

    suite_data = validate_suite(suite)
    pptx_renderer = (
        Path(str(skill_paths["presentations_root"]))
        / "container_tools"
        / "render_slides.py"
    ).resolve()
    if not pptx_renderer.is_file():
        raise ValueError(
            "sealed Presentations candidate does not provide render_slides.py"
        )
    cli_version = subprocess.run(
        [codex_bin, "--version"],
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    by_case: dict[str, list[PreparedRun]] = {}
    for run in prepared:
        by_case.setdefault(run.case_id, []).append(run)
    execution_results: list[dict[str, Any]] = []
    for case in suite_data["cases"]:
        execution_results.extend(
            _execute_pair(
                by_case[str(case["id"])],
                codex_bin=codex_bin,
                model=model,
                reasoning_effort=reasoning_effort,
            )
        )

    result_by_key = {
        (result["prepared"].case_id, result["prepared"].output_format): result
        for result in execution_results
    }
    run_records: list[dict[str, Any]] = []
    for case in suite_data["cases"]:
        pair = by_case[str(case["id"])]
        for prepared_run in pair:
            result = result_by_key[(prepared_run.case_id, prepared_run.output_format)]
            metrics = result["metrics"]
            task_manifest_before_checks = _verify_prepared_task(prepared_run)
            checks, artifact = perform_mechanical_checks(
                prepared_run, case, pptx_renderer=pptx_renderer
            )
            read_audit = _audit_commands(
                metrics["tool_inputs"],
                prepared_run,
                [run for run in prepared if run is not prepared_run],
            )
            run_records.append(
                {
                    "case_id": prepared_run.case_id,
                    "format": prepared_run.output_format,
                    "duration_ms": result["duration_ms"],
                    "total_tokens": metrics["total_tokens"],
                    "input_tokens": metrics["input_tokens"],
                    "cached_input_tokens": metrics["cached_input_tokens"],
                    "output_tokens": metrics["output_tokens"],
                    "noncached_input_plus_output_tokens": metrics["input_tokens"]
                    - metrics["cached_input_tokens"]
                    + metrics["output_tokens"],
                    "tool_calls": metrics["tool_calls"],
                    "process_exit_code": result["process_exit_code"],
                    "execution_identity": {
                        "model": model,
                        "reasoning_effort": reasoning_effort,
                        "enforced_by": "codex_cli_explicit_override",
                        "skill_identity": dict(
                            skill_identity[
                                (
                                    "clara"
                                    if prepared_run.output_format == "HTML"
                                    else "presentations"
                                )
                            ]
                        ),
                        "event_observed_models": metrics["observed_models"],
                        "event_observed_reasoning_efforts": metrics[
                            "observed_reasoning_efforts"
                        ],
                    },
                    "protocol": {
                        "ephemeral": True,
                        "isolated_workdir": str(prepared_run.workdir),
                        "output_root": str(prepared_run.output_root),
                        "prompt_sha256": _sha256_bytes(
                            prepared_run.prompt.encode("utf-8")
                        ),
                        "normalized_prompt_sha256": _sha256_bytes(
                            prepared_run.normalized_prompt.encode("utf-8")
                        ),
                        "source_manifest_sha256": prepared_run.source_manifest_sha256,
                        "source_manifest_verified": True,
                        "sealed_task_manifest_sha256": task_manifest_before_checks,
                        "sealed_task_verified_before_after": (
                            result["task_manifest_before"]
                            == prepared_run.task_manifest_sha256
                            == result["task_manifest_after"]
                            == task_manifest_before_checks
                        ),
                        "event_log_sha256": _sha256_file(result["event_log"]),
                        "thread_id": metrics["thread_id"],
                        "read_audit": read_audit,
                        "started_at": result["started_at"],
                        "completed_at": result["completed_at"],
                    },
                    "artifact": artifact,
                    "checks": checks,
                }
            )

    baseline_renders = _render_baselines(
        suite_data, prepared, output_root, pptx_renderer=pptx_renderer
    )
    packet_mappings = _create_review_packets(
        output_root, run_records, baseline_renders, prepared
    )
    candidate = {
        "schema_version": RUN_SCHEMA,
        "suite_id": suite["suite_id"],
        "protocol_evidence": {
            "producer": "run_clara_deck_benchmark.py",
            "suite_fingerprint_sha256": _canonical_sha256(suite),
            "codex_cli_version": cli_version,
            "recorded_at": _iso_now(),
            "candidate_skill_identity": {
                name: dict(identity) for name, identity in skill_identity.items()
            },
            "candidate_skill_paths": dict(skill_paths),
            "baseline_evidence_manifests": suite_data["baseline_manifest_by_case"],
            "review_packet_mappings": packet_mappings,
        },
        "runs": run_records,
        "semantic_reviews": [],
    }
    output = output_root / "candidate_runs.json"
    output.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    review_template = _semantic_review_template(
        suite_data, run_records, packet_mappings
    )
    (output_root / "semantic_review_template.json").write_text(
        json.dumps(review_template, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "evals"
        / "html_deck_capability_benchmarks.json",
    )
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="xhigh")
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--installed-clara-root", type=Path)
    parser.add_argument("--presentations-root", type=Path)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Launch four paid Codex runs. Without this flag, only verify and prepare.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        suite = _json_mapping(
            json.loads(args.suite.expanduser().resolve().read_text(encoding="utf-8")),
            label="suite",
        )
        fixture_config = _json_mapping(
            suite.get("fixture_root"), label="suite.fixture_root"
        )
        skill_identity, skill_paths = verify_candidate_skill_identity(
            suite,
            installed_clara_root=args.installed_clara_root,
            presentations_root=args.presentations_root,
        )
        fixture_root = args.fixture_root
        if fixture_root is None:
            environment_name = str(fixture_config["environment_variable"])
            fixture_root = Path(
                os.environ.get(environment_name, str(fixture_config["default"]))
            )
        prepared = prepare_benchmark(
            suite,
            fixture_root=fixture_root.expanduser().resolve(),
            output_root=args.output_root,
        )
        LOGGER.info("Prepared %d sealed benchmark runs", len(prepared))
        if not args.execute:
            LOGGER.info("Preparation only; add --execute to launch paid Codex runs")
            return 0
        candidate = execute_benchmark(
            suite,
            prepared,
            output_root=args.output_root.expanduser().resolve(),
            codex_bin=args.codex_bin,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            skill_identity=skill_identity,
            skill_paths=skill_paths,
        )
        LOGGER.info("Wrote runner-derived candidate records to %s", candidate)
        LOGGER.info(
            "Complete blinded model and human reviews in semantic_review_template.json, then copy them into candidate_runs.json before summarizing."
        )
        return 0
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        ValueError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as exc:
        LOGGER.error("error: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
