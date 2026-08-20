from __future__ import annotations

import json
from pathlib import Path

__all__: list[str] = []

ROOT = Path(__file__).resolve().parents[2]
CLARA_ROOT = ROOT / "plugins" / "clara"
SKILL_ROOT = CLARA_ROOT / "skills" / "advisory-case-director"


def _skill() -> str:
    """Read the case-director instructions."""

    return (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")


def _operating_model() -> str:
    """Read the case-director operating reference."""

    return (SKILL_ROOT / "references" / "operating-model.md").read_text(
        encoding="utf-8"
    )


def _normalized(text: str) -> str:
    """Collapse Markdown line wrapping for semantic phrase assertions."""

    return " ".join(text.split())


def test_case_director_owns_semantic_direction_without_a_universal_schema() -> None:
    skill = _skill()

    assert "The case director owns semantic direction" in skill
    assert "best current answer to the decision" in skill
    assert "case-specific reasoning structure" in skill
    assert "universal hypothesis schemas" in skill
    assert "fixed issue trees" in skill
    assert "Use judgement, not a numeric score" in skill
    assert "Deterministic helpers may" in skill
    assert "They do not decide whether a claim is true" in skill


def test_case_director_uses_markdown_spine_and_structured_cumulative_lineage() -> None:
    text = _normalized(_skill() + "\n" + _operating_model())

    assert (
        "`advisory_workpaper.md` is the current human-readable semantic spine" in text
    )
    assert "required meanings, not required headings" in text
    for filename in (
        "case_manifest.json",
        "clara_mandate.json",
        "material_registry.json",
        "advisory_evidence_register.json",
        "advisory_claim_register.json",
        "judgement_log.json",
        "open_questions.json",
        "case_brief.md",
    ):
        assert filename in text
    assert "Do not duplicate every receipt in the workpaper" in text
    assert "Do not let a new iteration replace earlier evidence" in text
    assert "history/advisory_workpaper.<timestamp>.md" in text
    assert "what the evidence proves and does not prove" in text
    assert "A transcript receipt proves that the speaker made" in text
    assert "link resulting open questions to that judgement entry" in text


def test_case_director_integrates_evidence_before_revising_the_story() -> None:
    skill = _normalized(_skill())
    operating_model = _normalized(_operating_model())

    assert skill.index("**Integrate before narrating.**") < skill.index(
        "**Say what changed.**"
    )
    assert "register the artifact or source" in operating_model
    assert "preserve claims that have been superseded or weakened" in operating_model
    assert "commit the staged workpaper" in operating_model
    assert "silently drops prior evidence" in skill
    assert "commit_advisory_workpaper.py" in skill
    assert "advisory_workpaper_checkpoint.json" in operating_model
    assert "Do not edit the canonical `advisory_workpaper.md` directly" in skill


def test_case_director_binds_deep_research_to_one_decision_question() -> None:
    skill = _normalized(_skill())

    assert "Before launching research, write a bounded brief" in skill
    for requirement in (
        "the decision and current answer",
        "the exact question the research must resolve",
        "the competing explanations or hypotheses",
        "the evidence that would weaken or disconfirm the current answer",
        "the boundary between a market-level conclusion and target-specific execution",
    ):
        assert requirement in skill
    assert "cannot prove that the target captures it" in skill
    assert "Do not browse automatically" in skill


def test_case_director_treats_specialists_and_decks_as_bounded_contributions() -> None:
    skill = _normalized(_skill())
    operating_model = _normalized(_operating_model())

    assert "A data-analysis orchestrator is a bounded contributor" in skill
    assert "Their manifests and outputs do not become a second project spine" in skill
    assert "The deck or memo is a view of the case, not the memory of the case" in skill
    assert "Do not wait until all analysis is finished" in skill
    assert "Do not rebuild the deliverable after every research action" in skill
    assert "Semantic feedback always returns to the spine" in operating_model
    assert "not separate inner and outer loops" in operating_model
    assert "verify_advisory_html_delivery.py" in operating_model


def test_case_director_routing_and_privacy_contract_are_registered() -> None:
    fixture = json.loads(
        (CLARA_ROOT / "evals" / "trigger_fixtures.json").read_text(encoding="utf-8")
    )
    routes = {
        item["id"]: item.get("expected_skill") for item in fixture["should_trigger"]
    }
    privacy = json.loads(
        (
            CLARA_ROOT / "privacy" / "workflows" / "advisory-case-director.json"
        ).read_text(encoding="utf-8")
    )

    assert routes["advisory-case-current-answer-and-next-work"] == (
        "clara:advisory-case-director"
    )
    assert routes["advisory-case-integrate-contradictory-research"] == (
        "clara:advisory-case-director"
    )
    assert routes["advisory-case-semantic-deck-feedback"] == (
        "clara:advisory-case-director"
    )
    assert privacy["workflow"] == "advisory-case-director"
    boundary = privacy["boundaries_beyond_codex"][0]
    assert boundary["kind"] == "public_research"
    assert boundary["requires_confirmation"] is True
    assert "explicit authorization" in " ".join(boundary["controls"])


def test_case_director_semantic_evals_cover_the_learned_failure_modes() -> None:
    suite = json.loads(
        (SKILL_ROOT / "evals" / "case_direction_cases.json").read_text(encoding="utf-8")
    )
    cases = {case["id"]: case for case in suite["cases"]}

    assert suite["schema_version"] == "1.0"
    assert "must not be derived by deterministic keywords" in suite["purpose"]
    assert set(cases) == {
        "initial-market-answer-without-target-data",
        "new-evidence-weakens-single-cause",
        "deep-research-answer-opens-target-question",
        "partner-question-changes-the-analysis",
        "semantic-deck-feedback-round-trip",
        "bounded-data-contribution",
    }
    assert (
        "target captures that pool"
        in cases["initial-market-answer-without-target-data"]["expected_current_answer"]
    )
    assert (
        "weaken"
        in cases["new-evidence-weakens-single-cause"]["expected_effect"].lower()
    )
    assert (
        "workpaper first"
        in cases["semantic-deck-feedback-round-trip"]["expected_effect"]
    )
    assert "owner of the overall case thesis" in " ".join(
        cases["bounded-data-contribution"]["must_not"]
    )


def test_planner_hands_durable_case_to_case_director_once() -> None:
    planner = (CLARA_ROOT / "skills" / "advisory-brief-planner" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    router = (CLARA_ROOT / "skills" / "clara" / "SKILL.md").read_text(encoding="utf-8")

    assert "handoff normally goes to `clara:advisory-case-director`" in planner
    assert "It is not rerun for each case iteration" in _skill()
    assert "route it to `advisory-case-director`" in router
    assert "it does not own a second semantic spine" in _normalized(router).lower()
