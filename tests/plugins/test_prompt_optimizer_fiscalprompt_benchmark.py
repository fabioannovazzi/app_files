from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "prompt-optimizer"
RUNNER_PATH = PLUGIN_ROOT / "scripts" / "run_fiscalprompt_benchmark.py"
SUMMARY_PATH = PLUGIN_ROOT / "scripts" / "summarize_fiscalprompt_benchmark.py"
SUITE_PATH = PLUGIN_ROOT / "evals" / "fiscalprompt_benchmark_suite.json"


def _load_script(module_name: str, path: Path):
    scripts_dir = str(path.parent)
    sys.path.insert(0, scripts_dir)
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(scripts_dir)


def _suite(*, minimum_complete_pairs: int = 1) -> dict[str, Any]:
    return {
        "schema_version": "prompt_optimizer.fiscalprompt_benchmark_suite.v1",
        "suite_id": "test-suite",
        "repeats_per_case": 1,
        "reviewer_policy": {"required_reviewer_types": ["model", "tax_professional"]},
        "rubric": {
            "prompt_dimensions": [
                {"id": "fact_preservation", "weight": 1.0, "description": "Facts"}
            ],
            "answer_dimensions": [
                {
                    "id": "substantive_correctness",
                    "weight": 1.0,
                    "description": "Correctness",
                }
            ],
            "hard_failures": ["material_legal_or_tax_error"],
        },
        "decision_policy": {
            "minimum_complete_pairs": minimum_complete_pairs,
            "answer_noninferiority_floor": -0.1,
            "answer_superiority_margin": 0.2,
            "maximum_additional_optimizer_hard_failures": 0,
        },
        "cases": [
            {
                "id": "case-1",
                "fiscalprompt_template_id": "IVA-01",
                "question": "Valutare l'IVA per Alfa S.r.l. e EUR 10.000.",
                "jurisdiction": "Italia",
                "output_language": "it",
                "fact_anchors": ["Alfa S.r.l.", "EUR 10.000"],
                "review_focus": ["IVA"],
            }
        ],
    }


def _template_page(template_id: str = "IVA-01") -> str:
    return f"""FiscalPrompt PRO | Area IVA

{template_id} - Verifica trattamento

RUOLO
Agisci come commercialista.

CONTESTO
Cliente: [Denominazione]

OBIETTIVO
Verificare il trattamento.

ISTRUZIONI DI UTILIZZO NELLO STUDIO
Inserire i dati.

OUTPUT RICHIESTO
Analisi e checklist.

VINCOLI PROFESSIONALI
Citare norme e dichiarare incertezza.
"""


def _review(
    runner: Any,
    mapping: dict[str, Any],
    *,
    reviewer_type: str,
    reviewer_id: str,
    optimizer_score: int,
    fiscalprompt_score: int,
) -> dict[str, Any]:
    label_by_treatment = {
        treatment: label for label, treatment in mapping["treatment_by_label"].items()
    }
    scores = {}
    for label in ("A", "B"):
        treatment = mapping["treatment_by_label"][label]
        score = (
            optimizer_score if treatment == "optimize_prompt" else fiscalprompt_score
        )
        scores[label] = {
            "prompt": {"fact_preservation": score},
            "answer": {"substantive_correctness": score},
        }
    return {
        "schema_version": runner.REVIEW_SCHEMA,
        "packet_id": mapping["packet_id"],
        "reviewer": {
            "type": reviewer_type,
            "id": reviewer_id,
            "model": "review-model" if reviewer_type == "model" else None,
            "thread_id": f"review-thread-{reviewer_id}",
        },
        "artifact_hashes": mapping["artifacts"],
        "scores": scores,
        "hard_failures": {"A": [], "B": []},
        "pairwise_winner": {
            "prompt": label_by_treatment["optimize_prompt"],
            "answer": label_by_treatment["optimize_prompt"],
        },
        "rationale": {
            "A": "Independent assessment of A.",
            "B": "Independent assessment of B.",
            "comparison": "The higher score reflects the declared rubric.",
        },
    }


def _runs_payload(runner: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping = {
        "packet_id": "case-1-repeat-01",
        "case_id": "case-1",
        "repeat": 1,
        "treatment_by_label": {"A": "optimize_prompt", "B": "fiscalprompt"},
        "artifacts": {
            "A": {"answer_sha256": "a" * 64, "prompt_sha256": "b" * 64},
            "B": {"answer_sha256": "c" * 64, "prompt_sha256": "d" * 64},
        },
        "review_instructions_sha256": "e" * 64,
        "builder_thread_ids": {
            "optimize_prompt": "builder-op",
            "fiscalprompt": "builder-fp",
        },
    }
    runs = []
    for treatment in runner.TREATMENTS:
        runs.append(
            {
                "case_id": "case-1",
                "repeat": 1,
                "treatment": treatment,
                "duration_ms": 100,
                "metrics": {
                    "thread_id": f"builder-{treatment}",
                    "total_tokens": 100,
                    "noncached_tokens": 90,
                },
                "mechanical_checks": {
                    "process_succeeded": True,
                    "required_artifacts_exist": True,
                    "sources_json_valid": True,
                    "treatment_isolation": {"status": "pass", "violations": []},
                    "fact_anchors": {
                        "prompt": {"all_present": True},
                        "answer": {"all_present": True},
                    },
                },
            }
        )
    return (
        {
            "schema_version": runner.RUNS_SCHEMA,
            "suite_id": "test-suite",
            "runs": runs,
            "private_review_mappings": [mapping],
        },
        mapping,
    )


@pytest.mark.parametrize("template_id", ["IVA-01", "CI-25", "IVA-ADV-20"])
def test_extract_fiscalprompt_template_returns_selected_structured_page(
    template_id: str,
) -> None:
    runner = _load_script(f"fiscalprompt_runner_extract_{template_id}", RUNNER_PATH)
    pdf_text = "\f".join([_template_page("OTHER-01"), _template_page(template_id)])

    result = runner.extract_fiscalprompt_template(pdf_text, template_id)

    assert result.startswith(f"{template_id} - Verifica trattamento")
    assert "RUOLO" in result
    assert "VINCOLI PROFESSIONALI" in result
    assert "OTHER-01" not in result


def test_prepare_benchmark_keeps_pdf_outside_git_and_writes_sealed_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_script("fiscalprompt_runner_prepare", RUNNER_PATH)
    pdf_path = tmp_path / "FiscalPrompt.pdf"
    pdf_path.write_bytes(b"private-pdf")
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text("# Prompt Optimizer\n", encoding="utf-8")
    output_root = tmp_path / "benchmark-output"
    monkeypatch.setattr(runner, "_extract_pdf_text", lambda _path: _template_page())
    monkeypatch.setattr(runner, "_seal_tree", lambda _path: None)

    prepared = runner.prepare_benchmark(
        _suite(),
        pdf_path=pdf_path,
        output_root=output_root,
        optimizer_skill_path=skill_path,
        repo_root=ROOT,
    )

    plan = json.loads((output_root / "benchmark_plan.json").read_text(encoding="utf-8"))
    assert len(prepared) == 2
    assert plan["source_receipt"]["pdf_copied_into_git"] is False
    assert not any(path.suffix == ".pdf" for path in output_root.rglob("*"))
    baseline_templates = list(output_root.rglob("fiscalprompt_template.md"))
    assert len(baseline_templates) == 1
    assert "IVA-01" in baseline_templates[0].read_text(encoding="utf-8")


def test_summarize_benchmark_requires_tax_professional_review() -> None:
    runner = _load_script("fiscalprompt_runner_incomplete", RUNNER_PATH)
    summary_mod = _load_script("fiscalprompt_summary_incomplete", SUMMARY_PATH)
    runs, mapping = _runs_payload(runner)
    model_review = _review(
        runner,
        mapping,
        reviewer_type="model",
        reviewer_id="model-1",
        optimizer_score=5,
        fiscalprompt_score=3,
    )

    summary = summary_mod.summarize_benchmark(_suite(), runs, [model_review])

    assert summary["status"] == "incomplete"
    assert summary["benchmark_passed"] is None
    assert summary["review_coverage"]["missing_reviews"] == [
        {
            "packet_id": "case-1-repeat-01",
            "reviewer_type": "tax_professional",
        }
    ]


def test_summarize_benchmark_maps_blinded_scores_after_complete_review() -> None:
    runner = _load_script("fiscalprompt_runner_complete", RUNNER_PATH)
    summary_mod = _load_script("fiscalprompt_summary_complete", SUMMARY_PATH)
    runs, mapping = _runs_payload(runner)
    reviews = [
        _review(
            runner,
            mapping,
            reviewer_type="model",
            reviewer_id="model-1",
            optimizer_score=5,
            fiscalprompt_score=3,
        ),
        _review(
            runner,
            mapping,
            reviewer_type="tax_professional",
            reviewer_id="tax-1",
            optimizer_score=4,
            fiscalprompt_score=3,
        ),
    ]

    summary = summary_mod.summarize_benchmark(_suite(), runs, reviews)

    assert summary["status"] == "complete"
    assert summary["outcome"] == "optimizer_superior"
    assert summary["benchmark_passed"] is True
    assert summary["semantic"]["mean_answer_delta"] == 1.5
    assert summary["semantic"]["winner_counts"]["answer"] == {"optimize_prompt": 2}


def test_validate_review_rejects_builder_thread_as_reviewer() -> None:
    runner = _load_script("fiscalprompt_runner_self_review", RUNNER_PATH)
    summary_mod = _load_script("fiscalprompt_summary_self_review", SUMMARY_PATH)
    _, mapping = _runs_payload(runner)
    review = _review(
        runner,
        mapping,
        reviewer_type="model",
        reviewer_id="model-1",
        optimizer_score=4,
        fiscalprompt_score=3,
    )
    review["reviewer"]["thread_id"] = "builder-op"

    with pytest.raises(ValueError, match="reviewer thread"):
        summary_mod.validate_review(
            review,
            suite=_suite(),
            packet_mapping=mapping,
        )


def test_treatment_isolation_audit_rejects_optimizer_reading_baseline(
    tmp_path: Path,
) -> None:
    runner = _load_script("fiscalprompt_runner_isolation", RUNNER_PATH)
    output_root = tmp_path / "benchmark"
    optimizer_workdir = output_root / "runs" / "case" / "repeat-01" / "optimize_prompt"
    baseline_workdir = output_root / "runs" / "case" / "repeat-01" / "fiscalprompt"
    optimizer_task = output_root / "sealed_tasks" / "optimizer"
    baseline_task = output_root / "sealed_tasks" / "fiscalprompt"
    optimizer = runner.PreparedRun(
        "case",
        1,
        "optimize_prompt",
        optimizer_workdir,
        optimizer_task,
        "a" * 64,
        "run",
    )
    baseline = runner.PreparedRun(
        "case",
        1,
        "fiscalprompt",
        baseline_workdir,
        baseline_task,
        "b" * 64,
        "run",
    )
    plan = {
        "source_receipt": {"pdf_path": str(tmp_path / "source.pdf")},
        "candidate_identity": {
            "skill_path": str(
                tmp_path / "plugin" / "skills" / "prompt-optimizer" / "SKILL.md"
            )
        },
    }

    audit = runner._audit_treatment_isolation(
        optimizer,
        metrics={"tool_inputs": [f'{{"path": "{baseline_task}"}}']},
        all_runs=[optimizer, baseline],
        plan=plan,
    )

    assert audit["status"] == "fail"
    assert str(baseline_task) in audit["violations"]


def test_treatment_isolation_audit_rejects_installed_optimizer_skill_in_baseline(
    tmp_path: Path,
) -> None:
    runner = _load_script("fiscalprompt_runner_installed_skill", RUNNER_PATH)
    output_root = tmp_path / "prompt-optimizer-fiscalprompt-benchmark"
    baseline = runner.PreparedRun(
        "case",
        1,
        "fiscalprompt",
        output_root / "runs" / "case" / "repeat-01" / "fiscalprompt",
        output_root / "sealed_tasks" / "case" / "repeat-01" / "fiscalprompt",
        "a" * 64,
        "run",
    )
    installed_skill = (
        tmp_path
        / ".codex"
        / "plugins"
        / "cache"
        / "vera"
        / "skills"
        / "prompt-optimizer"
        / "SKILL.md"
    )
    plan = {
        "source_receipt": {"pdf_path": str(tmp_path / "source.pdf")},
        "candidate_identity": {
            "skill_path": str(
                ROOT
                / "plugins"
                / "prompt-optimizer"
                / "skills"
                / "prompt-optimizer"
                / "SKILL.md"
            )
        },
    }

    audit = runner._audit_treatment_isolation(
        baseline,
        metrics={"tool_inputs": [f'{{"path": "{installed_skill}"}}']},
        all_runs=[baseline],
        plan=plan,
    )

    assert audit == {
        "status": "fail",
        "violations": ["prompt_optimizer_skill_reference"],
    }


def test_treatment_isolation_audit_allows_optimizer_own_output_root_name(
    tmp_path: Path,
) -> None:
    runner = _load_script("fiscalprompt_runner_own_root", RUNNER_PATH)
    output_root = tmp_path / "prompt-optimizer-fiscalprompt-benchmark"
    optimizer = runner.PreparedRun(
        "case",
        1,
        "optimize_prompt",
        output_root / "runs" / "case" / "repeat-01" / "optimize_prompt",
        output_root / "sealed_tasks" / "case" / "repeat-01" / "optimize_prompt",
        "a" * 64,
        "run",
    )
    plan = {
        "source_receipt": {"pdf_path": str(tmp_path / "source.pdf")},
        "candidate_identity": {
            "skill_path": str(
                ROOT
                / "plugins"
                / "prompt-optimizer"
                / "skills"
                / "prompt-optimizer"
                / "SKILL.md"
            )
        },
    }

    audit = runner._audit_treatment_isolation(
        optimizer,
        metrics={"tool_inputs": [f'{{"path": "{optimizer.workdir}"}}']},
        all_runs=[optimizer],
        plan=plan,
    )

    assert audit == {"status": "pass", "violations": []}


def test_treatment_isolation_audit_allows_optimizer_checking_own_output_labels(
    tmp_path: Path,
) -> None:
    runner = _load_script("fiscalprompt_runner_own_output_check", RUNNER_PATH)
    output_root = tmp_path / "prompt-optimizer-fiscalprompt-benchmark"
    optimizer = runner.PreparedRun(
        "case",
        1,
        "optimize_prompt",
        output_root / "runs" / "case" / "repeat-01" / "optimize_prompt",
        output_root / "sealed_tasks" / "case" / "repeat-01" / "optimize_prompt",
        "a" * 64,
        "run",
    )
    plan = {
        "source_receipt": {"pdf_path": str(tmp_path / "source.pdf")},
        "candidate_identity": {
            "skill_path": str(
                ROOT
                / "plugins"
                / "prompt-optimizer"
                / "skills"
                / "prompt-optimizer"
                / "SKILL.md"
            )
        },
    }

    audit = runner._audit_treatment_isolation(
        optimizer,
        metrics={
            "tool_inputs": [
                '{"command": "rg -ni benchmark|treatment|FiscalPrompt result"}'
            ]
        },
        all_runs=[optimizer],
        plan=plan,
    )

    assert audit == {"status": "pass", "violations": []}


def test_treatment_isolation_audit_rejects_optimizer_fiscalprompt_web_search(
    tmp_path: Path,
) -> None:
    runner = _load_script("fiscalprompt_runner_web_search", RUNNER_PATH)
    output_root = tmp_path / "benchmark"
    optimizer = runner.PreparedRun(
        "case",
        1,
        "optimize_prompt",
        output_root / "runs" / "case" / "repeat-01" / "optimize_prompt",
        output_root / "sealed_tasks" / "case" / "repeat-01" / "optimize_prompt",
        "a" * 64,
        "run",
    )
    plan = {
        "source_receipt": {"pdf_path": str(tmp_path / "source.pdf")},
        "candidate_identity": {"skill_path": str(tmp_path / "candidate.md")},
    }

    audit = runner._audit_treatment_isolation(
        optimizer,
        metrics={"tool_inputs": ['{"query": "FiscalPrompt IVA template"}']},
        all_runs=[optimizer],
        plan=plan,
    )

    assert audit == {
        "status": "fail",
        "violations": ["fiscalprompt_search_query"],
    }


def test_launch_run_disables_automatic_plugins_and_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _load_script("fiscalprompt_runner_launch_config", RUNNER_PATH)
    task_root = tmp_path / "task"
    workdir = tmp_path / "work"
    task_root.mkdir()
    workdir.mkdir()
    run = runner.PreparedRun(
        "case",
        1,
        "fiscalprompt",
        workdir,
        task_root,
        "a" * 64,
        "run",
    )
    recorded_command: list[str] = []

    def fake_run(command: list[str], **_kwargs: Any):
        recorded_command.extend(command)
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": (
                    b'{"type":"thread.started","thread_id":"thread-1"}\n'
                    b'{"type":"turn.completed","usage":'
                    b'{"input_tokens":1,"cached_input_tokens":0,'
                    b'"output_tokens":1}}\n'
                ),
                "stderr": b"",
            },
        )()

    monkeypatch.setattr(runner, "_verify_task", lambda _run: None)
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    runner._launch_run(
        run,
        codex_bin="codex",
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
    )

    assert "--ignore-user-config" in recorded_command
    disabled = [
        recorded_command[index + 1]
        for index, value in enumerate(recorded_command)
        if value == "--disable"
    ]
    assert disabled == list(runner.CODEX_DISABLED_FEATURES)


def test_review_file_discovery_ignores_packet_metadata(tmp_path: Path) -> None:
    summary_mod = _load_script("fiscalprompt_summary_review_files", SUMMARY_PATH)
    packet = tmp_path / "review_packets" / "packet-1"
    reviews = packet / "reviews"
    reviews.mkdir(parents=True)
    (packet / "case.json").write_text("{}", encoding="utf-8")
    (packet / "review_template.json").write_text("{}", encoding="utf-8")
    completed_review = reviews / "model.json"
    completed_review.write_text("{}", encoding="utf-8")

    discovered = summary_mod._review_files(tmp_path / "review_packets")

    assert discovered == [completed_review]


def test_committed_suite_has_declared_full_matrix_and_quality_boundary() -> None:
    runner = _load_script("fiscalprompt_runner_suite", RUNNER_PATH)
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))

    validated = runner.validate_suite(suite)

    assert len(validated["cases"]) == 8
    assert validated["repeats"] == 2
    assert suite["decision_policy"]["minimum_complete_pairs"] == 16
    assert "tax_professional" in validated["required_reviewer_types"]
    assert (
        suite["decision_policy"][
            "cost_is_reported_but_cannot_offset_quality_regression"
        ]
        is True
    )
