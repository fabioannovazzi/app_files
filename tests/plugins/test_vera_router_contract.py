from __future__ import annotations

import json
import re
from pathlib import Path

__all__: list[str] = []


ROOT = Path(__file__).resolve().parents[2]
VERA_ROOT = ROOT / "plugins" / "vera"
ROUTER_PATH = VERA_ROOT / "skills" / "vera" / "SKILL.md"
CATALOG_PATH = VERA_ROOT / "skills" / "vera" / "references" / "workflow-catalog.md"
MARKETPLACE_CARDS_PATH = VERA_ROOT / "marketplace_skill_instructions.json"
STUDIO_ARCHIVE_WRAPPER_PATH = VERA_ROOT / "skills" / "studio-archive" / "SKILL.md"


def _read_text(path: Path) -> str:
    """Return UTF-8 text for one Vera contract file."""

    return path.read_text(encoding="utf-8")


def test_vera_router_frontmatter_triggers_for_explicit_invocation() -> None:
    router = _read_text(ROUTER_PATH)

    frontmatter = router.split("---", maxsplit=2)[1]

    assert "whenever Vera is explicitly invoked" in frontmatter
    assert "including through @vera" in frontmatter
    assert "stop without answering when no specialist workflow matches" in frontmatter
    assert "capability gap" not in frontmatter
    assert "out of scope" not in frontmatter


def test_vera_router_defines_supported_and_no_match_outcomes() -> None:
    router = _read_text(ROUTER_PATH)

    required_contracts = (
        "Supported professional work",
        "No matching specialist workflow",
        "Do not fall back to general-assistant behavior inside Vera",
        "Vera workflow: vera:<specialist-skill>",
    )

    assert all(contract in router for contract in required_contracts)
    assert "Professional capability gap" not in router
    assert "Unrelated work" not in router
    assert "fourteen professional workflows" not in router


def test_vera_workflow_catalog_covers_every_specialist_skill() -> None:
    skill_root = VERA_ROOT / "skills"
    expected_skills = {path.parent.name for path in skill_root.glob("*/SKILL.md")} - {
        "vera"
    }
    catalog = _read_text(CATALOG_PATH)

    catalogued_skills = set(
        re.findall(r"^- `([a-z0-9-]+)`:", catalog, flags=re.MULTILINE)
    )

    assert catalogued_skills == expected_skills


def test_vera_routes_paolo_agenzia_teaching_request_to_studio_archive() -> None:
    router = _read_text(ROUTER_PATH)
    catalog = _read_text(CATALOG_PATH)
    wrapper = _read_text(STUDIO_ARCHIVE_WRAPPER_PATH)
    cards = json.loads(_read_text(MARKETPLACE_CARDS_PATH))["skills"]

    exact_request = (
        "Mostra a Vera come scaricare le fatture attive "
        "e passive dall’Agenzia delle Entrate"
    )

    assert "show or\n  teach Vera the Agenzia delle Entrate" in router
    assert "active/passive invoice-download and ZIP-retrieval" in catalog
    assert exact_request in " ".join(wrapper.split())
    assert (
        "select Studio Archive instead of the\n   no-matching-workflow outcome"
        in wrapper
    )
    assert (
        "registratore privacy-bounded di Codex Desktop"
        in cards["studio-archive"]["instructions"]
    )
    assert "Never look for `requirements.txt` or `scripts/`" in wrapper


def test_vera_validated_answer_route_is_automatic_but_not_a_filing_fallback() -> None:
    router = _read_text(ROUTER_PATH)
    question_workflow = _read_text(
        VERA_ROOT / "skills" / "quesito-professionale" / "SKILL.md"
    )
    prompt_optimizer = _read_text(
        VERA_ROOT / "skills" / "prompt-optimizer" / "SKILL.md"
    )
    validator = _read_text(
        VERA_ROOT / "skills" / "deep-research-validator" / "SKILL.md"
    )

    required_contracts = (
        "start one question-to-validated-answer journey",
        "select `quesito-professionale`",
        "vera:quesito-professionale -> vera:prompt-optimizer",
        "operational filing, statutory return, tax declaration, or form",
        "stop under the no-matching-specialist-workflow outcome",
        "Use automatically before Vera answers",
        "Use automatically before Vera delivers",
    )

    combined_contract = "\n".join(
        (router, question_workflow, prompt_optimizer, validator)
    )
    assert all(contract in combined_contract for contract in required_contracts)


def test_vera_trigger_fixtures_cover_explicit_scope_boundaries() -> None:
    fixtures = json.loads(
        (VERA_ROOT / "evals" / "trigger_fixtures.json").read_text(encoding="utf-8")
    )

    trigger_ids = {case["id"] for case in fixtures["should_trigger"]}
    non_trigger_ids = {case["id"] for case in fixtures["should_not_trigger"]}

    assert "vera-explicit-unrelated" in trigger_ids
    assert "vera-explicit-no-matching-workflow" in trigger_ids
    assert "vera-ordinary-legal-question" in trigger_ids
    assert "generic-pizza" in non_trigger_ids

    tenancy_case = next(
        case
        for case in fixtures["should_trigger"]
        if case["id"] == "vera-ordinary-legal-question"
    )
    assert tenancy_case["prompt"].startswith("@vera")
    assert "vera:quesito-professionale" in tenancy_case["required_signals"]


def test_vera_chatgpt_root_card_is_router_only_and_catalog_complete() -> None:
    payload = json.loads(_read_text(MARKETPLACE_CARDS_PATH))
    instructions = payload["skills"]["vera"]["instructions"]
    expected_specialists = {
        path.parent.name
        for path in (VERA_ROOT / "skills").glob("*/SKILL.md")
        if path.parent.name != "vera"
    }

    assert "opera esclusivamente come router" in instructions
    assert "non risponde mai direttamente alla richiesta sostanziale" in instructions
    assert "interpreta semanticamente la richiesta" in instructions
    assert (
        "Se nessun workflow elencato copre la richiesta, Vera si ferma" in instructions
    )
    assert "non risponde alla richiesta né offre percorsi alternativi" in instructions
    assert "privacy-surface-review" not in instructions
    assert all(
        f"`{skill_name}`" in instructions
        for skill_name in expected_specialists - {"privacy-surface-review"}
    )


def test_professional_question_is_an_orchestrator_not_a_third_data_workstream() -> None:
    components = json.loads(
        (VERA_ROOT / "components.json").read_text(encoding="utf-8")
    )
    workflow = _read_text(
        VERA_ROOT / "skills" / "quesito-professionale" / "SKILL.md"
    )

    assert "quesito-professionale" not in components["plugins"]
    assert not (
        VERA_ROOT / "privacy" / "workstreams" / "quesito-professionale.json"
    ).exists()
    assert "does not create a third client workstream" in workflow
    assert "does not create a third Studio Archive workstream" in _read_text(
        ROUTER_PATH
    )
