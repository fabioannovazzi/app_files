from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SUMMARY_SCRIPT = (
    ROOT / "plugins" / "clara" / "scripts" / "summarize_html_deck_benchmark.py"
)
RUNNER_SCRIPT = ROOT / "plugins" / "clara" / "scripts" / "run_clara_deck_benchmark.py"
SUITE = ROOT / "plugins" / "clara" / "evals" / "html_deck_capability_benchmarks.json"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_summary() -> Any:
    return load_module("clara_html_benchmark_summary", SUMMARY_SCRIPT)


def load_runner() -> Any:
    scripts = str(RUNNER_SCRIPT.parent)
    sys.path.insert(0, scripts)
    try:
        return load_module("clara_html_benchmark_runner", RUNNER_SCRIPT)
    finally:
        sys.path.remove(scripts)


def load_suite() -> dict[str, Any]:
    return json.loads(SUITE.read_text(encoding="utf-8"))


def canonical_sha256(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def render_set_sha256(render_hashes: list[str]) -> str:
    payload = "".join(
        f"{position}\0{render_hash}\n"
        for position, render_hash in enumerate(render_hashes, start=1)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def candidate_runs(
    suite: dict[str, Any], *, semantic_regression: bool = False
) -> dict[str, Any]:
    metrics = {
        ("create-two-slide-analytical-deck", "HTML"): (260000, 1900000, 28),
        ("create-two-slide-analytical-deck", "PPTX"): (280000, 2000000, 31),
        ("revise-two-slide-analytical-deck", "HTML"): (180000, 1200000, 20),
        ("revise-two-slide-analytical-deck", "PPTX"): (500000, 5000000, 60),
    }
    cases = {case["id"]: case for case in suite["cases"]}
    baseline = {
        (run["case_id"], run["format"]): run
        for run in suite["recorded_baseline"]["runs"]
    }
    runs: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    packet_mappings: list[dict[str, Any]] = []
    for position, ((case_id, output_format), values) in enumerate(
        metrics.items(), start=1
    ):
        duration, total_tokens, tool_calls = values
        artifact_sha = digest(f"candidate-{case_id}-{output_format}")
        workdir = Path("/tmp/clara-benchmark") / case_id / output_format.lower()
        output_root = workdir / "output"
        started_at = f"2026-07-14T10:{position // 3:02d}:00+00:00"
        completed_at = f"2026-07-14T10:{position // 3:02d}:30+00:00"
        checks = {
            name: True
            for name in cases[case_id]["required_checks_by_format"][output_format]
        }
        input_tokens = total_tokens - 50000
        render_hashes = [
            digest(f"render-{case_id}-{output_format}-{number}") for number in (1, 2)
        ]
        candidate_render_set_sha256 = render_set_sha256(render_hashes)
        baseline_render_set_sha256 = digest(
            f"current-baseline-render-set-{case_id}-{output_format}"
        )
        packet_id = f"packet-{position}"
        review_prompt_sha256 = digest(f"review-prompt-{position}")
        source_requirements_sha256 = digest(f"source-requirements-{position}")
        candidate_label = "A" if position % 2 else "B"
        baseline_label = "B" if candidate_label == "A" else "A"
        skill_name = "clara" if output_format == "HTML" else "presentations"
        runs.append(
            {
                "case_id": case_id,
                "format": output_format,
                "duration_ms": duration,
                "total_tokens": total_tokens,
                "input_tokens": input_tokens,
                "cached_input_tokens": 1000,
                "output_tokens": 50000,
                "noncached_input_plus_output_tokens": total_tokens - 1000,
                "tool_calls": tool_calls,
                "process_exit_code": 0,
                "execution_identity": {
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "xhigh",
                    "enforced_by": "codex_cli_explicit_override",
                    "skill_identity": suite["candidate_skill_identity"][skill_name],
                },
                "protocol": {
                    "ephemeral": True,
                    "isolated_workdir": str(workdir),
                    "output_root": str(output_root),
                    "prompt_sha256": digest(f"prompt-{case_id}-{output_format}"),
                    "normalized_prompt_sha256": digest(f"prompt-{case_id}"),
                    "source_manifest_sha256": cases[case_id]["source_manifest"][
                        "manifest_sha256"
                    ],
                    "source_manifest_verified": True,
                    "sealed_task_manifest_sha256": digest(
                        f"sealed-task-{case_id}-{output_format}"
                    ),
                    "sealed_task_verified_before_after": True,
                    "event_log_sha256": digest(f"event-{case_id}-{output_format}"),
                    "thread_id": f"builder-thread-{position}",
                    "read_audit": "pass",
                    "started_at": started_at,
                    "completed_at": completed_at,
                },
                "artifact": {
                    "path": str(
                        output_root
                        / ("index.html" if output_format == "HTML" else "deck.pptx")
                    ),
                    "sha256": artifact_sha,
                    "bytes": 12345,
                    "render_set_sha256": candidate_render_set_sha256,
                    "rendered_slides": [
                        {
                            "path": str(output_root / f"slide-{number}.png"),
                            "sha256": render_hashes[number - 1],
                            "bytes": 4567,
                            "width": 1280,
                            "height": 720,
                            "renderer": (
                                "playwright-chromium"
                                if output_format == "HTML"
                                else "presentations-render_slides"
                            ),
                        }
                        for number in (1, 2)
                    ],
                },
                "checks": checks,
            }
        )
        scores_by_label = {}
        for label in ("A", "B"):
            scores_by_label[label] = {}
            for dimension in suite["semantic_judgement"]["dimensions"]:
                score = (
                    3
                    if label == candidate_label
                    and semantic_regression
                    and case_id == "create-two-slide-analytical-deck"
                    and output_format == "HTML"
                    and dimension == "visual_hierarchy"
                    else 4
                )
                scores_by_label[label][dimension] = {
                    "score": score,
                    "pass": score >= 4,
                    "rationale": (
                        "Blinded label review found equivalent evidence and design quality."
                    ),
                }
        reviews.append(
            {
                "case_id": case_id,
                "format": output_format,
                "reviewer": {
                    "type": "model",
                    "id": f"blinded-review-{position}",
                    "model": "gpt-5.6-sol",
                    "thread_id": f"review-thread-{position}",
                },
                "review_packet_id": packet_id,
                "review_prompt_sha256": review_prompt_sha256,
                "source_requirements_sha256": source_requirements_sha256,
                "candidate_artifact_sha256": artifact_sha,
                "baseline_artifact_sha256": baseline[(case_id, output_format)][
                    "artifact_sha256"
                ],
                "candidate_render_set_sha256": candidate_render_set_sha256,
                "baseline_render_set_sha256": baseline_render_set_sha256,
                "scores_by_label": scores_by_label,
                "overall_rationale": "All four dimensions were reviewed without format identity.",
            }
        )
        packet_mappings.append(
            {
                "packet_id": packet_id,
                "case_id": case_id,
                "format": output_format,
                "candidate_label": candidate_label,
                "baseline_label": baseline_label,
                "prompt_sha256": review_prompt_sha256,
                "source_requirements_sha256": source_requirements_sha256,
                "candidate_render_set_sha256": candidate_render_set_sha256,
                "baseline_render_set_sha256": baseline_render_set_sha256,
            }
        )
    return {
        "schema_version": "clara.html_deck_benchmark_runs.v1",
        "suite_id": suite["suite_id"],
        "protocol_evidence": {
            "producer": "run_clara_deck_benchmark.py",
            "suite_fingerprint_sha256": canonical_sha256(suite),
            "codex_cli_version": "codex-cli 1.0",
            "recorded_at": "2026-07-14T10:00:00+00:00",
            "candidate_skill_identity": suite["candidate_skill_identity"],
            "candidate_skill_paths": {
                "clara_root": f"/tmp/clara/{suite['candidate_skill_identity']['clara']['version']}",
                "presentations_root": (
                    "/tmp/presentations/"
                    f"{suite['candidate_skill_identity']['presentations']['version']}"
                    "/skills/presentations"
                ),
            },
            "baseline_evidence_manifests": {
                case["id"]: case["baseline_evidence"]["manifest_sha256"]
                for case in suite["cases"]
            },
            "review_packet_mappings": packet_mappings,
        },
        "runs": runs,
        "semantic_reviews": reviews,
    }


def test_summarize_benchmark_passes_controlled_non_regressing_gain() -> None:
    module = load_summary()
    suite = load_suite()

    report = module.summarize_benchmark(suite, candidate_runs(suite))

    assert report["result"] == "pass"
    assert report["target_checks"]["protocol_controls"] is True
    assert report["target_checks"]["mechanical_quality"] is True
    assert report["target_checks"]["semantic_non_regression"] is True
    assert report["target_checks"]["html_median_token_improvement"] is True
    assert report["target_checks"]["html_median_duration_improvement"] is True
    assert report["html_median_improvement"]["tokens_percent"] >= 30


def test_summarize_benchmark_rejects_mechanical_regression_despite_savings() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["runs"][0]["checks"]["browser_qa"] = False

    report = module.summarize_benchmark(suite, candidate)

    assert report["result"] == "fail"
    assert report["target_checks"]["mechanical_quality"] is False


def test_summarize_benchmark_rejects_blinded_semantic_regression() -> None:
    module = load_summary()
    suite = load_suite()

    report = module.summarize_benchmark(
        suite, candidate_runs(suite, semantic_regression=True)
    )

    assert report["result"] == "fail"
    assert report["target_checks"]["semantic_non_regression"] is False


def test_summarize_benchmark_requires_suite_declared_model_reviews() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["semantic_reviews"].pop()

    report = module.summarize_benchmark(suite, candidate)

    assert report["result"] == "fail"
    assert any("missing_model_review" in item for item in report["semantic_failures"])


def test_summarize_benchmark_allows_optional_genuine_human_review() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    human_review = deepcopy(candidate["semantic_reviews"][0])
    human_review["reviewer"] = {
        "type": "human",
        "id": "independent-human-01",
        "model": None,
        "thread_id": "human-review-thread-01",
    }
    candidate["semantic_reviews"].append(human_review)

    report = module.summarize_benchmark(suite, candidate)

    assert report["target_checks"]["semantic_non_regression"] is True


def test_summarize_benchmark_rejects_review_artifact_hash_mismatch() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["semantic_reviews"][0]["candidate_artifact_sha256"] = digest(
        "wrong-artifact"
    )

    with pytest.raises(ValueError, match="candidate artifact hash mismatch"):
        module.summarize_benchmark(suite, candidate)


def test_summarize_benchmark_rejects_review_render_hash_mismatch() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["semantic_reviews"][0]["candidate_render_set_sha256"] = digest(
        "wrong-render-set"
    )

    with pytest.raises(ValueError, match="candidate render-set mismatch"):
        module.summarize_benchmark(suite, candidate)


def test_summarize_benchmark_rejects_builder_as_model_reviewer() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["semantic_reviews"][0]["reviewer"]["thread_id"] = candidate["runs"][0][
        "protocol"
    ]["thread_id"]

    with pytest.raises(ValueError, match="disjoint from builders"):
        module.summarize_benchmark(suite, candidate)


def test_summarize_benchmark_rejects_reused_model_reviewer_thread() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["semantic_reviews"][1]["reviewer"]["thread_id"] = candidate[
        "semantic_reviews"
    ][0]["reviewer"]["thread_id"]

    with pytest.raises(ValueError, match="unique across packets"):
        module.summarize_benchmark(suite, candidate)


def test_summarize_benchmark_rejects_reviewer_thread_from_different_builder() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["semantic_reviews"][0]["reviewer"]["thread_id"] = candidate["runs"][1][
        "protocol"
    ]["thread_id"]

    with pytest.raises(ValueError, match="disjoint from builders"):
        module.summarize_benchmark(suite, candidate)


def test_summarize_benchmark_rejects_manually_unblinded_review_scores() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["semantic_reviews"][0]["dimensions"] = {
        "visual_hierarchy": {"candidate_score": 5, "baseline_score": 1}
    }

    with pytest.raises(ValueError, match="retain raw A/B scores"):
        module.summarize_benchmark(suite, candidate)


def test_summarize_benchmark_requires_token_and_duration_improvements() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["runs"][0]["duration_ms"] = 550000
    candidate["runs"][1]["duration_ms"] = 600000
    candidate["runs"][2]["duration_ms"] = 450000

    report = module.summarize_benchmark(suite, candidate)

    assert report["target_checks"]["html_median_token_improvement"] is True
    assert report["target_checks"]["html_median_duration_improvement"] is False
    assert report["target_checks"]["create_duration_ratio"] is True
    assert report["target_checks"]["revise_duration_ratio"] is True
    assert report["result"] == "fail"


@pytest.mark.parametrize("invalid", [1.5, float("nan"), float("inf")])
def test_summarize_benchmark_rejects_fractional_or_non_finite_counts(
    invalid: float,
) -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["runs"][0]["total_tokens"] = invalid

    with pytest.raises(ValueError, match="positive integer"):
        module.summarize_benchmark(suite, candidate)


def test_summarize_benchmark_rejects_candidate_matrix_mismatch() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["runs"].pop()

    with pytest.raises(ValueError, match="candidate run matrix mismatch"):
        module.summarize_benchmark(suite, candidate)


def test_validate_suite_rejects_gate_not_declared_at_top_level() -> None:
    module = load_summary()
    suite = load_suite()
    suite["cases"][0]["required_checks_by_format"]["HTML"].append("undeclared_check")

    with pytest.raises(ValueError, match="undeclared gates"):
        module.validate_suite(suite)


def test_validate_suite_rejects_baseline_matrix_mismatch() -> None:
    module = load_summary()
    suite = load_suite()
    suite["recorded_baseline"]["runs"].pop()

    with pytest.raises(ValueError, match="baseline run matrix"):
        module.validate_suite(suite)


def test_protocol_controls_are_derived_from_evidence_not_boolean_claims() -> None:
    module = load_summary()
    suite = load_suite()
    candidate = candidate_runs(suite)
    candidate["runs"][0]["protocol"]["read_audit"] = "fail"

    report = module.summarize_benchmark(suite, candidate)

    assert report["protocol_controls"]["no_prior_run_or_opposite_format_reads"] is False
    assert "no_prior_run_or_opposite_format_reads" in report["failed_controls"]


def test_build_prompt_varies_only_target_format() -> None:
    runner = load_runner()
    html_prompt, html_normalized = runner.build_prompt(
        output_format="HTML",
        instruction_path=Path("/tmp/task.txt"),
        spec_path=Path("/tmp/spec.json"),
    )
    pptx_prompt, pptx_normalized = runner.build_prompt(
        output_format="PPTX",
        instruction_path=Path("/tmp/task.txt"),
        spec_path=Path("/tmp/spec.json"),
    )

    assert html_normalized == pptx_normalized
    assert (
        html_prompt.replace("TARGET_FORMAT: HTML", "TARGET_FORMAT: PPTX") == pptx_prompt
    )


def test_parse_codex_jsonl_records_usage_and_unique_tool_calls() -> None:
    runner = load_runner()
    payload = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "tool-1",
                        "type": "command_execution",
                        "command": "pwd",
                        "aggregated_output": "../../fixture/path appeared in output",
                    },
                }
            ),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 25,
                        "output_tokens": 20,
                    },
                }
            ),
        ]
    ).encode("utf-8")

    result = runner.parse_codex_jsonl(payload)

    assert result["thread_id"] == "thread-1"
    assert result["total_tokens"] == 120
    assert result["tool_calls"] == 1
    assert result["commands"] == ["pwd"]
    assert result["tool_inputs"] == ['{"command": "pwd"}']


def test_parse_codex_jsonl_preserves_unicode_line_separator_inside_event() -> None:
    runner = load_runner()
    events = [
        {"type": "thread.started", "thread_id": "thread-1"},
        {
            "type": "item.completed",
            "item": {
                "id": "tool-1",
                "type": "command_execution",
                "command": "inspect dependency",
                "aggregated_output": "before\u0085after",
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 25,
                "output_tokens": 20,
            },
        },
    ]
    payload = (
        "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n"
    ).encode("utf-8")

    result = runner.parse_codex_jsonl(payload)

    assert b"\xc2\x85" in payload
    assert result["thread_id"] == "thread-1"
    assert result["total_tokens"] == 120
    assert result["tool_calls"] == 1


@pytest.mark.parametrize(
    "tool_input_kind", ["traversal", "other_run", "source_fixture"]
)
def test_read_audit_rejects_out_of_scope_reads(
    tmp_path: Path, tool_input_kind: str
) -> None:
    runner = load_runner()

    def prepared(output_format: str) -> Any:
        workdir = tmp_path / "experiment" / output_format.lower()
        return runner.PreparedRun(
            case_id="case",
            mode="create",
            output_format=output_format,
            workdir=workdir,
            output_root=workdir / "output",
            artifact_path=workdir / "output" / "artifact",
            rendered_paths=(),
            prompt="prompt",
            normalized_prompt="normalized",
            source_manifest_sha256=digest("manifest"),
            fixture_source=tmp_path / "sealed" / "case",
            task_root=workdir / "task",
            task_spec=workdir / "task" / "spec.json",
            task_manifest_sha256=digest("task-manifest"),
            task_manifest_path=workdir / "task-manifest.json",
        )

    html = prepared("HTML")
    pptx = prepared("PPTX")
    tool_inputs = {
        "traversal": "cat ../../prior.json",
        "other_run": f"cat {pptx.artifact_path}",
        "source_fixture": f"cat {html.fixture_source / 'common/task.txt'}",
    }

    assert (
        runner._audit_commands([tool_inputs[tool_input_kind]], html, [pptx]) == "fail"
    )


def test_read_audit_allows_current_absolute_output_path(tmp_path: Path) -> None:
    runner = load_runner()
    workdir = tmp_path / "experiment" / "html"
    output_root = workdir / "output"
    prepared = runner.PreparedRun(
        case_id="case",
        mode="create",
        output_format="HTML",
        workdir=workdir,
        output_root=output_root,
        artifact_path=output_root / "index.html",
        rendered_paths=(),
        prompt="prompt",
        normalized_prompt="normalized",
        source_manifest_sha256=digest("manifest"),
        fixture_source=tmp_path / "fixtures" / "case",
        task_root=tmp_path / "sealed-tasks" / "html",
        task_spec=tmp_path / "sealed-tasks" / "html" / "spec.json",
        task_manifest_sha256=digest("task-manifest"),
        task_manifest_path=tmp_path / "manifests" / "html.json",
    )

    result = runner._audit_commands([f"mkdir -p {output_root}"], prepared, [])

    assert result == "pass"


def test_verify_source_manifest_detects_tampering(tmp_path: Path) -> None:
    runner = load_runner()
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    source = fixture / "input.txt"
    source.write_text("sealed", encoding="utf-8")
    file_hash = hashlib.sha256(b"sealed").hexdigest()
    manifest_hash = hashlib.sha256(f"input.txt\0{file_hash}\n".encode()).hexdigest()
    case = {
        "id": "case",
        "fixture_subdirectory": "fixture",
        "source_manifest": {
            "manifest_sha256": manifest_hash,
            "files": [{"path": "input.txt", "sha256": file_hash}],
        },
    }
    assert runner.verify_source_manifest(case, tmp_path) == fixture.resolve()
    source.write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        runner.verify_source_manifest(case, tmp_path)


@pytest.mark.parametrize(
    "relative_path",
    ["spec.json", "assets/chart.png", "baseline/deck.pptx"],
)
def test_verify_prepared_task_rejects_mutated_sealed_inputs(
    tmp_path: Path, relative_path: str
) -> None:
    runner = load_runner()
    workdir = tmp_path / "run"
    task_root = tmp_path / "sealed-task"
    (task_root / "assets").mkdir(parents=True)
    (task_root / "baseline").mkdir()
    (task_root / "spec.json").write_text('{"slide_count": 2}', encoding="utf-8")
    (task_root / "assets" / "chart.png").write_bytes(b"chart")
    (task_root / "baseline" / "deck.pptx").write_bytes(b"deck")
    workdir.mkdir()
    (workdir / "task").symlink_to(task_root, target_is_directory=True)
    manifest_sha256, _ = runner._task_tree_manifest(task_root)
    prepared = runner.PreparedRun(
        case_id="case",
        mode="revise",
        output_format="PPTX",
        workdir=workdir,
        output_root=workdir / "output",
        artifact_path=workdir / "output" / "deck.pptx",
        rendered_paths=(),
        prompt="prompt",
        normalized_prompt="normalized",
        source_manifest_sha256=digest("source"),
        fixture_source=tmp_path / "fixture",
        task_root=task_root,
        task_spec=task_root / "spec.json",
        task_manifest_sha256=manifest_sha256,
        task_manifest_path=tmp_path / "task-manifest.json",
    )
    (task_root / relative_path).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="sealed task tree changed"):
        runner._verify_prepared_task(prepared)


@pytest.mark.parametrize("tree_kind", ["clara", "presentations"])
def test_candidate_tree_hash_changes_when_runtime_script_changes(
    tmp_path: Path, tree_kind: str
) -> None:
    runner = load_runner()
    runtime = tmp_path / "runtime"
    (runtime / "scripts").mkdir(parents=True)
    script = runtime / "scripts" / "build.py"
    script.write_text("VERSION = 1\n", encoding="utf-8")
    hash_tree = (
        runner._plugin_runtime_tree_sha256
        if tree_kind == "clara"
        else runner._directory_tree_sha256
    )
    before = hash_tree(runtime)
    script.write_text("VERSION = 2\n", encoding="utf-8")

    after = hash_tree(runtime)

    assert after != before


def test_visible_slide_parser_keeps_copy_after_self_closing_image(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    artifact = tmp_path / "index.html"
    artifact.write_text(
        '<section class="slide"><p>Before</p><img src="chart.png" /><p>After</p></section>',
        encoding="utf-8",
    )

    nodes = runner._visible_slide_nodes(artifact, "HTML")

    assert nodes == [["Before", "After"]]


def test_exact_visible_copy_rejects_post_image_mutation(tmp_path: Path) -> None:
    runner = load_runner()
    artifact = tmp_path / "index.html"
    artifact.write_text(
        '<section class="slide"><p>Before</p><img src="chart.png" /><p>Changed</p></section>',
        encoding="utf-8",
    )

    passed = runner._exact_visible_copy(
        artifact, "HTML", [["Before", "Expected after image"]]
    )

    assert passed is False


def test_revision_structure_parser_detects_post_image_structure_mutation(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    baseline = tmp_path / "baseline.html"
    revised = tmp_path / "revised.html"
    baseline.write_text(
        '<section class="slide"><img src="chart.png" /><div class="preserved">After</div></section>',
        encoding="utf-8",
    )
    revised.write_text(
        '<section class="slide"><img src="chart.png" /><div class="mutated">After</div></section>',
        encoding="utf-8",
    )
    baseline_slides, _ = runner._html_revision_inventory(baseline)

    revised_slides, _ = runner._html_revision_inventory(revised)

    assert revised_slides != baseline_slides


def test_sealed_historical_create_html_passes_exact_copy_when_available() -> None:
    runner = load_runner()
    fixture = ROOT / "output" / "deck_format_controlled_experiment_20260713"
    spec_path = fixture / "common" / "deck_spec.json"
    artifact = fixture / "html_output" / "index.html"
    if not spec_path.is_file() or not artifact.is_file():
        pytest.skip("external sealed benchmark creation fixture is unavailable")
    deck_spec = json.loads(spec_path.read_text(encoding="utf-8"))

    passed = runner._exact_visible_copy(
        artifact, "HTML", runner._create_expected_slide_nodes(deck_spec)
    )

    assert passed is True


@pytest.mark.parametrize(
    "relationship_target",
    ["/ppt/media/chart.png", "../media/chart.png"],
)
def test_pptx_slide_asset_hashes_resolve_absolute_and_relative_relationships(
    tmp_path: Path, relationship_target: str
) -> None:
    runner = load_runner()
    artifact = tmp_path / "deck.pptx"
    image_bytes = b"representative-chart-bytes"
    relationships = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="image" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{relationship_target}" />
</Relationships>
"""
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" />',
        )
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", relationships)
        archive.writestr("ppt/media/chart.png", image_bytes)

    observed = runner._slide_asset_hashes(artifact, "PPTX")

    assert observed == [{hashlib.sha256(image_bytes).hexdigest()}]


@pytest.mark.parametrize("output_format", ["HTML", "PPTX"])
def test_sealed_historical_revision_passes_fidelity_contract_when_available(
    output_format: str,
) -> None:
    runner = load_runner()
    fixture = ROOT / "output" / "deck_format_change_experiment_20260713"
    spec_path = fixture / "common" / "change_spec.json"
    artifact = (
        fixture / "html_output" / "index.html"
        if output_format == "HTML"
        else fixture / "pptx_output" / "global_superstore_revised.pptx"
    )
    if not spec_path.is_file() or not artifact.is_file():
        pytest.skip("external sealed benchmark revision fixture is unavailable")
    revision_spec = json.loads(spec_path.read_text(encoding="utf-8"))

    passed = (
        runner._html_revision_fidelity(revision_spec, artifact)
        if output_format == "HTML"
        else runner._pptx_revision_fidelity(revision_spec, artifact)
    )

    assert passed is True


def test_rewrite_create_task_copies_common_assets_and_hides_opposite_target(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    fixture = tmp_path / "fixture"
    common = fixture / "common"
    assets = common / "assets"
    assets.mkdir(parents=True)
    (assets / "chart.png").write_bytes(b"sealed-chart")
    (common / "task.txt").write_text("Build the deck.", encoding="utf-8")
    (common / "spec.json").write_text(
        json.dumps(
            {
                "target_outputs": {
                    "HTML": {"root": "/sealed/html", "artifact": "index.html"},
                    "PPTX": {"root": "/sealed/pptx", "artifact": "deck.pptx"},
                }
            }
        ),
        encoding="utf-8",
    )
    case = {
        "mode": "create",
        "instruction_file": "common/task.txt",
        "spec_file": "common/spec.json",
        "source_manifest": {
            "files": [{"path": "common/assets/chart.png", "sha256": digest("chart")}]
        },
    }
    workdir = tmp_path / "html-run"

    task_spec = runner._rewrite_task_spec(
        case,
        fixture_source=fixture,
        workdir=workdir,
        output_format="HTML",
    )

    rewritten = json.loads(task_spec.read_text(encoding="utf-8"))
    assert set(rewritten["target_outputs"]) == {"HTML"}
    assert "/sealed/pptx" not in task_spec.read_text(encoding="utf-8")
    assert (workdir / "task" / "assets" / "chart.png").read_bytes() == b"sealed-chart"


def test_rewrite_revision_task_copies_only_selected_format_baseline(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    fixture = tmp_path / "fixture"
    common = fixture / "common"
    html_input = fixture / "html_input"
    pptx_input = fixture / "pptx_input"
    common.mkdir(parents=True)
    (html_input / "assets").mkdir(parents=True)
    pptx_input.mkdir(parents=True)
    (common / "task.txt").write_text("Revise the deck.", encoding="utf-8")
    (html_input / "index.html").write_text("<main></main>", encoding="utf-8")
    (html_input / "styles.css").write_text("main {}", encoding="utf-8")
    (html_input / "assets" / "chart.png").write_bytes(b"html-chart")
    (pptx_input / "deck.pptx").write_bytes(b"pptx-baseline")
    (common / "spec.json").write_text(
        json.dumps(
            {
                "baselines": {
                    "HTML": {"root": "/sealed/html", "artifact": "index.html"},
                    "PPTX": {"root": "/sealed/pptx", "artifact": "deck.pptx"},
                },
                "target_outputs": {
                    "HTML": {"root": "/target/html", "artifact": "index.html"},
                    "PPTX": {"root": "/target/pptx", "artifact": "deck.pptx"},
                },
            }
        ),
        encoding="utf-8",
    )
    case = {
        "mode": "revise",
        "instruction_file": "common/task.txt",
        "spec_file": "common/spec.json",
        "source_manifest": {
            "files": [
                {"path": "html_input/index.html", "sha256": digest("html")},
                {"path": "html_input/styles.css", "sha256": digest("css")},
                {"path": "html_input/assets/chart.png", "sha256": digest("chart")},
                {"path": "pptx_input/deck.pptx", "sha256": digest("pptx")},
            ]
        },
    }
    workdir = tmp_path / "html-revision"

    task_spec = runner._rewrite_task_spec(
        case,
        fixture_source=fixture,
        workdir=workdir,
        output_format="HTML",
    )

    rewritten = json.loads(task_spec.read_text(encoding="utf-8"))
    assert set(rewritten["baselines"]) == {"HTML"}
    assert set(rewritten["target_outputs"]) == {"HTML"}
    assert (workdir / "task" / "baseline" / "index.html").is_file()
    assert (workdir / "task" / "baseline" / "styles.css").is_file()
    assert (workdir / "task" / "baseline" / "assets" / "chart.png").is_file()
    assert not any(workdir.rglob("*.pptx"))
    assert "PPTX" not in task_spec.read_text(encoding="utf-8")


def test_review_packet_randomizes_labels_and_binds_sanitized_requirements(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    workdir = tmp_path / "run"
    task_root = workdir / "task"
    output_root = workdir / "output"
    task_root.mkdir(parents=True)
    output_root.mkdir()
    task_spec = task_root / "spec.json"
    task_spec.write_text(
        json.dumps(
            {
                "experiment": {"slide_count": 2},
                "baselines": {"HTML": {"root": "/hidden/baseline"}},
                "target_outputs": {"HTML": {"root": "/hidden/target"}},
            }
        ),
        encoding="utf-8",
    )
    (task_root / "task.txt").write_text("Preserve exact copy.", encoding="utf-8")
    (task_root / "assets").mkdir()
    (task_root / "assets" / "chart.png").write_bytes(b"source-chart")
    candidate_paths = [output_root / f"candidate-{number}.png" for number in (1, 2)]
    baseline_paths = [tmp_path / f"baseline-{number}.png" for number in (1, 2)]
    for path in candidate_paths + baseline_paths:
        path.write_bytes(path.name.encode("utf-8"))
    candidate_render_hash = digest("candidate-render-set")
    baseline_render_hash = digest("baseline-render-set")
    prepared = runner.PreparedRun(
        case_id="case",
        mode="create",
        output_format="HTML",
        workdir=workdir,
        output_root=output_root,
        artifact_path=output_root / "index.html",
        rendered_paths=tuple(candidate_paths),
        prompt="prompt",
        normalized_prompt="normalized",
        source_manifest_sha256=digest("manifest"),
        fixture_source=tmp_path / "sealed",
        task_root=task_root,
        task_spec=task_spec,
        task_manifest_sha256=digest("task-manifest"),
        task_manifest_path=tmp_path / "task-manifest.json",
    )
    run_records = [
        {
            "case_id": "case",
            "format": "HTML",
            "artifact": {
                "render_set_sha256": candidate_render_hash,
                "rendered_slides": [{"path": str(path)} for path in candidate_paths],
            },
        }
    ]
    baseline_renders = {
        ("case", "HTML"): {
            "render_set_sha256": baseline_render_hash,
            "rendered_slides": [{"path": str(path)} for path in baseline_paths],
        }
    }

    mappings = runner._create_review_packets(
        tmp_path / "benchmark", run_records, baseline_renders, [prepared]
    )

    mapping = mappings[0]
    packet = tmp_path / "benchmark" / "review_packets" / mapping["packet_id"]
    assert {mapping["candidate_label"], mapping["baseline_label"]} == {"A", "B"}
    requirements = json.loads(
        (packet / "source_requirements.json").read_text(encoding="utf-8")
    )
    assert requirements["task_brief"] == "Preserve exact copy."
    assert requirements["requirements"] == {"experiment": {"slide_count": 2}}
    assert (packet / "source_assets" / "chart.png").read_bytes() == b"source-chart"
    assert (
        mapping["source_requirements_sha256"]
        == hashlib.sha256(
            (packet / "source_requirements.json").read_bytes()
        ).hexdigest()
    )
