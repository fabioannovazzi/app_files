from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_plugin_review_contract import validate_contract

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "prompt-optimizer"
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
MCP_SERVER_PATH = PLUGIN_ROOT / "mcp" / "server.cjs"


def load_script(module_name: str, script_name: str):
    script_path = SCRIPTS_DIR / script_name
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPTS_DIR))


def _call_mcp_server(
    method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    if shutil.which("node") is None:
        pytest.skip("node is required for MCP server checks")
    request = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    completed = subprocess.run(
        ["node", str(MCP_SERVER_PATH)],
        input=json.dumps(request) + "\n",
        capture_output=True,
        check=True,
        text=True,
    )
    responses = [
        json.loads(line)
        for line in completed.stdout.splitlines()
        if line.strip().startswith("{")
    ]
    assert responses
    response = responses[-1]
    assert "error" not in response
    return response["result"]


def test_inspect_question_extracts_deterministic_anchors(tmp_path: Path) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question", "inspect_question.py"
    )
    question = (
        "Italian company Alfa S.r.l. paid EUR 1,250,000 on 31/12/2025 "
        "and asks whether VAT applies under EU rules. What sources should be checked?"
    )

    paths = inspect_mod.write_inspection(question, tmp_path, "en")
    inventory = json.loads(paths["question_inventory"].read_text(encoding="utf-8"))
    recipe = json.loads(paths["prompt_recipe"].read_text(encoding="utf-8"))

    assert inventory["language_hint"] in {"en", "auto"}
    assert "31/12/2025" in inventory["dates"]
    assert any("1,250,000" in amount for amount in inventory["amounts"])
    assert "European Union" in inventory["jurisdiction_hints"]
    assert inventory["explicit_questions"] == ["What sources should be checked?"]
    assert recipe["lens"]["scope"] == "domestic_plus_EU"
    assert recipe["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert recipe["jurisdiction_policy"]["policy_source"] == "inventory_only"
    framework_labels = {
        framework["label"]
        for framework in recipe["jurisdiction_policy"]["possible_frameworks"]
    }
    assert "Italian law" in framework_labels
    assert "European Union law" in framework_labels
    assert recipe["jurisdiction_conflicts"] == []
    assert recipe["source_domains"] == []
    assert recipe["source_domain_policy"] == "model_curated_only"
    assert "source hierarchy" in recipe["required_prompt_elements"]
    assert (
        "user-facing jurisdiction assumption notice"
        in recipe["required_prompt_elements"]
    )
    assert (
        "explicit research lens with posture, objective, and scope"
        in recipe["required_prompt_elements"]
    )
    assert recipe["lawyer_intake"]["mode"] == "ask_before_drafting_when_material"


def test_inspect_question_requires_angle_before_domain_choices(
    tmp_path: Path,
) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question_angle", "inspect_question.py"
    )
    question = (
        "What is the legal status, in terms of EU law and other liabilities, "
        "of an entity that provides plugins that help tax accountants solve "
        "fiscal issues for their customers?"
    )

    paths = inspect_mod.write_inspection(question, tmp_path, "en")
    recipe = json.loads(paths["prompt_recipe"].read_text(encoding="utf-8"))

    angle_confirmation = recipe["angle_confirmation"]
    assert angle_confirmation["required"] is True
    assert angle_confirmation["mode"] == "structured_choice"
    assert "research angle" in angle_confirmation["reason"]
    angle_option_ids = {option["id"] for option in angle_confirmation["options"]}
    assert "legal_status_classification" in angle_option_ids
    assert "liability_risk_matrix" in angle_option_ids
    assert "compliance_operating_model" in angle_option_ids
    assert recipe["lawyer_intake"]["angle_confirmation_required"] is True
    assert recipe["lawyer_intake"]["questions"][0]["id"] == "angle_confirmation"

    assert recipe["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert recipe["jurisdiction_policy"]["selection_status"] == "unconfirmed"
    jurisdiction_confirmation = recipe["jurisdiction_confirmation"]
    assert jurisdiction_confirmation["required"] is True
    assert jurisdiction_confirmation["mode"] == "structured_choice"
    assert "national law" in jurisdiction_confirmation["reason"]
    jurisdiction_option_ids = {
        option["id"] for option in jurisdiction_confirmation["options"]
    }
    assert "eu_law_baseline" in jurisdiction_option_ids
    assert "eu_plus_member_state" in jurisdiction_option_ids
    assert recipe["lawyer_intake"]["jurisdiction_confirmation_required"] is True
    intake_question_ids = {item["id"] for item in recipe["lawyer_intake"]["questions"]}
    assert "jurisdiction_confirmation" in intake_question_ids


def test_inspect_question_sets_french_geneva_jurisdiction(
    tmp_path: Path,
) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question_fr", "inspect_question.py"
    )
    question = (
        "Comment traiter fiscalement une donation de CHF 20 000 en 2025? "
        "Quelles sources verifier?"
    )

    paths = inspect_mod.write_inspection(question, tmp_path, "fr")
    recipe = json.loads(paths["prompt_recipe"].read_text(encoding="utf-8"))

    assert recipe["effective_language"] == "fr"
    assert recipe["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert recipe["jurisdiction_policy"]["possible_frameworks"]


def test_inspect_question_keeps_jurisdiction_independent_from_output_language(
    tmp_path: Path,
) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question_en_geneva", "inspect_question.py"
    )
    question = (
        "Please answer in English. A taxpayer in Geneva, Switzerland needs to "
        "challenge a cantonal tax assessment. What sources should be checked?"
    )

    paths = inspect_mod.write_inspection(question, tmp_path, "en")
    inventory = json.loads(paths["question_inventory"].read_text(encoding="utf-8"))
    recipe = json.loads(paths["prompt_recipe"].read_text(encoding="utf-8"))

    assert "Canton of Geneva" in inventory["jurisdiction_hints"]
    assert recipe["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert recipe["jurisdiction_policy"]["policy_source"] == "inventory_only"
    framework_labels = {
        framework["label"]
        for framework in recipe["jurisdiction_policy"]["possible_frameworks"]
    }
    assert "Swiss law and Canton of Geneva" in framework_labels
    assert recipe["jurisdiction_conflicts"] == []
    assert recipe["source_domains"] == []
    assert recipe["source_domain_policy"] == "model_curated_only"


def test_inspect_question_does_not_semantically_route_broad_legal_question(
    tmp_path: Path,
) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question_broad_succession", "inspect_question.py"
    )
    question = (
        "A French national domiciled in Geneva for 18 years dies in 2026. "
        "He leaves a second wife, children, a Geneva apartment, a chalet in "
        "Valais, Singapore bank accounts, a French SCI and a Jersey trust. "
        "The will disinherits a child, an inheritance pact benefits the wife, "
        "and trust transfers are challenged for capacity, undue influence and "
        "fraudulent depletion. Which law governs under Swiss private "
        "international law? Do Geneva courts have jurisdiction? How does "
        "forced heirship apply? Can the will or pact be challenged? Can the "
        "trust be clawed back? How does the matrimonial property regime "
        "interact? What interim protective measures exist? What tax "
        "consequences arise?"
    )

    paths = inspect_mod.write_inspection(question, tmp_path, "en")
    inventory = json.loads(paths["question_inventory"].read_text(encoding="utf-8"))
    recipe = json.loads(paths["prompt_recipe"].read_text(encoding="utf-8"))
    complexity = recipe["complexity_profile"]

    assert inventory["requires_phased_workflow"] is False
    assert inventory["topic_flags"] == []
    assert complexity["requires_phased_workflow"] is False
    assert complexity["recommended_phases"] == []
    assert complexity["required_controls"] == []
    assert recipe["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert recipe["jurisdiction_policy"]["policy_source"] == "inventory_only"
    framework_hints = {
        framework["hint"]
        for framework in recipe["jurisdiction_policy"]["possible_frameworks"]
    }
    assert "Canton of Geneva" in framework_hints
    assert "France" in framework_hints
    assert recipe["source_domains"] == []
    assert recipe["source_domain_policy"] == "model_curated_only"


def test_inspect_question_does_not_generate_domains_for_italian_tenancy(
    tmp_path: Path,
) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question_italian_tenancy", "inspect_question.py"
    )
    question = (
        "Under Italian law, a tenant signs a contratto di locazione abitativa in Milan for "
        "EUR 1,200 per month. After two years, the landlord says his son will "
        "live there under Article 3 of Law 431/1998. The apartment is then "
        "re-rented, placed on Airbnb, or sold."
    )

    paths = inspect_mod.write_inspection(question, tmp_path, "en")
    inventory = json.loads(paths["question_inventory"].read_text(encoding="utf-8"))
    recipe = json.loads(paths["prompt_recipe"].read_text(encoding="utf-8"))

    assert "Italy" in inventory["jurisdiction_hints"]
    assert inventory["topic_flags"] == []
    assert inventory["requires_phased_workflow"] is False
    assert recipe["source_domains"] == []
    assert recipe["source_domain_policy"] == "model_curated_only"


def test_inspect_question_builds_lawyer_intake_for_dispute_letter(
    tmp_path: Path,
) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question_dispute", "inspect_question.py"
    )
    question = (
        "Mio son in Germany, at the home of his grandmother, left his computer "
        "on with torrent enabled. Grandmother received a cease and desist "
        "letter accusing her of sharing a film."
    )

    paths = inspect_mod.write_inspection(question, tmp_path, "auto")
    recipe = json.loads(paths["prompt_recipe"].read_text(encoding="utf-8"))
    intake = recipe["lawyer_intake"]

    assert recipe["lens"]["posture"] == "defense_audit_dispute"
    assert recipe["lens"]["objective"] == "balanced"
    assert intake["mode"] == "ask_before_drafting_when_material"
    assert intake["max_questions"] == 5
    question_ids = {item["id"] for item in intake["questions"]}
    assert "deadline_and_dates" in question_ids
    assert "demands_and_sender" in question_ids
    assert "parties_and_roles" in question_ids
    assert "jurisdiction_confirmation" in question_ids
    assert intake["output_format_options"][0]["id"] == "response_strategy"


def test_inspect_question_rejects_empty_cli_input(tmp_path: Path) -> None:
    inspect_mod = load_script(
        "prompt_optimizer_inspect_question_empty", "inspect_question.py"
    )
    question_file = tmp_path / "question.txt"
    question_file.write_text("", encoding="utf-8")

    assert inspect_mod.inspect_question_text("").character_count == 0


def test_validate_prompt_passes_complete_prompt(tmp_path: Path) -> None:
    validate_mod = load_script("prompt_optimizer_validate_prompt", "validate_prompt.py")
    question = (
        "Italian company Alfa S.r.l. paid EUR 1,250,000 on 31/12/2025. "
        "What sources should be checked?"
    )
    prompt = """
You are a tax lawyer. Mandatory output language: English.
Jurisdiction assumption: use Italian law.
Research lens: posture is assessment_ex_post, objective is balanced, scope is domestic_plus_EU.
Assumed output format: client-ready legal memo.
Preserve these facts: Italian company Alfa S.r.l. paid EUR 1,250,000 on 31/12/2025.
Answer the explicit question: What sources should be checked?
Use official sources, primary legislation, tax authority guidance, case law and stable URLs.
Source domains: normattiva.it, agenziaentrate.gov.it, eur-lex.europa.eu.
Use citations [1], [2] and a final notes section.
Ask up to three clarifying questions if essential facts are missing.
Structure the output with premises, analysis, conclusions and notes.
Flag residual uncertainty.
"""

    paths = validate_mod.write_validation(question, prompt, tmp_path, language="en")
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))
    run_intake = json.loads((tmp_path / "run_intake.json").read_text(encoding="utf-8"))
    review_payload = json.loads(
        (tmp_path / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (tmp_path / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (tmp_path / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert audit["status"] == "pass"
    assert audit["failed_checks"] == []
    assert audit["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert audit["jurisdiction_policy"]["policy_source"] == "inventory_only"
    assert audit["jurisdiction_policy"]["policy_source"] == "inventory_only"
    assert audit["source_domains"] == [
        "https://normattiva.it/",
        "https://agenziaentrate.gov.it/",
        "https://eur-lex.europa.eu/",
    ]
    assert audit["source_domain_policy"] == "model_curated_only"
    assert (
        paths["source_domains"].read_text(encoding="utf-8")
        == "https://normattiva.it/\nhttps://agenziaentrate.gov.it/\nhttps://eur-lex.europa.eu/\n"
    )
    assert (
        paths["source_domains_comma"].read_text(encoding="utf-8")
        == "https://normattiva.it/, https://agenziaentrate.gov.it/, https://eur-lex.europa.eu/\n"
    )
    assert (
        paths["optimized_prompt"]
        .read_text(encoding="utf-8")
        .strip()
        .startswith("You are a tax lawyer.")
    )
    package_text = paths["prompt_package"].read_text(encoding="utf-8")
    assert "Prompt Optimizer Package" in package_text
    assert "Paste `source_domains_comma.txt`" in package_text
    assert "## Optimized Prompt\nYou are a tax lawyer." not in package_text
    assert audit["review_session"]["run_id"] == run_intake["run_id"]
    assert review_payload["plugin"] == "prompt-optimizer"
    assert review_payload["workflow"] == "prompt-optimizer"
    assert review_payload["run_id"] == run_intake["run_id"]
    assert review_payload["review_type"] == "prompt_optimizer_review"
    assert review_payload["item_count"] == len(review_payload["items"])
    item_types = {item["item_type"] for item in review_payload["items"]}
    assert "prompt_artifact" in item_types
    assert "source_domain_artifact" in item_types
    assert "review_artifact" in item_types
    assert review_payload["summary"]["audit_status"] == "pass"
    assert review_payload["summary"]["source_domain_count"] == 3
    assert ui_decisions["status"] == "pending_review"
    assert ui_decisions["decision_count"] == 0
    assert final_artifacts["status"] == "written_pending_review"
    handoff_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "review_handoff.md"
    )
    handoff_text = (tmp_path / "review_handoff.md").read_text(encoding="utf-8")
    assert handoff_output["required_text"] == [
        "Review Handoff",
        "review_payload.json",
        "ui_decisions.json",
        "applied_decisions.json",
        "final_artifacts.json",
    ]
    assert "render_prompt_optimizer_review" in handoff_text
    assert "apply_prompt_optimizer_decisions" in handoff_text
    prompt_package_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "prompt_package.md"
    )
    assert prompt_package_output["required_text"] == [
        "# Prompt Optimizer Package",
        "## Deterministic Research Lens",
        "## What to Use",
    ]
    readme_output = next(
        output
        for output in final_artifacts["outputs"]
        if output["path"] == "README_HUMAN.md"
    )
    assert readme_output["required_text"] == [
        "# How to use these files",
        "Paste `optimized_prompt.md` into Deep Research.",
    ]
    assert paths["review_payload"] == tmp_path / "review_payload.json"
    contract_report = validate_contract(
        tmp_path,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()


def test_validate_prompt_accepts_english_output_for_swiss_geneva_law(
    tmp_path: Path,
) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_en_geneva", "validate_prompt.py"
    )
    question = (
        "Please answer in English. A taxpayer in Geneva, Switzerland needs to "
        "challenge a cantonal tax assessment. What sources should be checked?"
    )
    prompt = """
You are a Swiss tax lawyer. Mandatory output language: English.
Jurisdiction assumption: use Swiss law and Canton of Geneva.
Research lens: posture is defense_audit_dispute, objective is balanced, scope is domestic_only.
Assumed output format: response strategy memo.
Preserve these facts: taxpayer in Geneva, Switzerland; cantonal tax assessment.
Answer the explicit question: What sources should be checked?
Use official sources, primary legislation, tax authority guidance, case law and stable URLs.
Source domains: fedlex.admin.ch, ge.ch.
Use citations [1], [2] and a final notes section.
Ask up to three clarifying questions if essential facts are missing.
Structure the output with premises, analysis, conclusions and notes.
Flag residual uncertainty.
"""

    paths = validate_mod.write_validation(question, prompt, tmp_path, language="en")
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))

    assert audit["status"] == "pass"
    assert audit["failed_checks"] == []
    assert audit["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert audit["jurisdiction_policy"]["policy_source"] == "inventory_only"
    assert audit["source_domains"] == [
        "https://fedlex.admin.ch/",
        "https://ge.ch/",
    ]
    assert audit["source_domain_policy"] == "model_curated_only"
    assert (
        paths["optimized_prompt"]
        .read_text(encoding="utf-8")
        .strip()
        .startswith("You are a Swiss tax lawyer.")
    )
    assert "Prompt Optimizer Package" in paths["prompt_package"].read_text(
        encoding="utf-8"
    )


def test_spanish_validation_package_and_review_artifacts_are_localized(
    tmp_path: Path,
) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_spanish", "validate_prompt.py"
    )
    question = (
        "¿Qué tratamiento fiscal corresponde a una factura de 1.250 EUR "
        "emitida el 31/12/2025?"
    )
    prompt = """
Idioma de salida obligatorio: español.
Conserve los hechos, importes y fechas de la pregunta.
Separe el objetivo, el alcance y el derecho aplicable.
Use fuentes oficiales, legislación primaria, jurisprudencia y URL estables.
Incluya citas, conclusiones, límites y preguntas aclaratorias esenciales.
"""

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        language="es",
        source_domains=["boe.es", "agenciatributaria.es"],
    )

    package = paths["prompt_package"].read_text(encoding="utf-8")
    readme = paths["readme_human"].read_text(encoding="utf-8")
    handoff = (tmp_path / "review_handoff.md").read_text(encoding="utf-8")
    review = json.loads((tmp_path / "review_payload.json").read_text(encoding="utf-8"))
    final_artifacts = json.loads(
        (tmp_path / "final_artifacts.json").read_text(encoding="utf-8")
    )

    assert "# Paquete de optimización del prompt" in package
    assert "## Cómo utilizar los archivos" in package
    assert "# Prompt Optimizer Package" not in package
    assert "# Cómo utilizar estos archivos" in readme
    assert "# Optimización del prompt · Entrega para revisión" in handoff
    assert "## Revisión en Codex" in handoff
    assert [column["label"] for column in review["columns"]] == [
        "Tipo",
        "Elemento del prompt",
        "Acción sugerida",
        "Fuente",
        "Salida",
        "Estado",
    ]
    artifact_titles = {item["title"] for item in review["items"]}
    assert "Prompt optimizado" in artifact_titles
    assert "Paquete del prompt en Markdown" in artifact_titles
    assert "Corrija draft_prompt.md" in final_artifacts["next_actions"][1]
    assert "Angle and jurisdiction choices" not in json.dumps(
        final_artifacts, ensure_ascii=False
    )
    contract_report = validate_contract(tmp_path, strict_output_content=True)
    assert contract_report.ok, contract_report.as_dict()


def test_validate_prompt_writes_source_domains_from_sidecar(
    tmp_path: Path,
) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_sidecar", "validate_prompt.py"
    )
    question = "Italian company Alfa S.r.l. asks what sources should be checked?"
    prompt = """
You are a tax lawyer. Mandatory output language: English.
Jurisdiction assumption: use Italian law.
Research lens: posture is assessment_ex_post, objective is balanced, scope is domestic_only.
Assumed output format: legal research brief.
Preserve these facts: Italian company Alfa S.r.l.
Answer the explicit question: what sources should be checked?
Use official sources, primary legislation, tax authority guidance, case law and stable URLs.
Use citations [1], [2] and a final notes section.
Ask up to three clarifying questions if essential facts are missing.
Structure the output with premises, analysis, conclusions and notes.
Flag residual uncertainty.
"""

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        language="en",
        source_domains=[
            "https://www.normattiva.it/",
            "agenziaentrate.gov.it",
        ],
    )
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))

    assert audit["source_domains"] == [
        "https://www.normattiva.it/",
        "https://agenziaentrate.gov.it/",
    ]
    assert (
        paths["source_domains_comma"].read_text(encoding="utf-8")
        == "https://www.normattiva.it/, https://agenziaentrate.gov.it/\n"
    )
    assert (
        paths["readme_human"]
        .read_text(encoding="utf-8")
        .startswith("# How to use these files")
    )


def test_validate_prompt_does_not_require_broad_matter_controls(
    tmp_path: Path,
) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_broad_missing", "validate_prompt.py"
    )
    question = (
        "A French national domiciled in Geneva for 18 years dies in 2026 with "
        "a second wife, children, a French matrimonial property regime, a will, "
        "an inheritance pact, a Jersey trust, Swiss and Singapore bank accounts, "
        "foreign assets, interim protective measures, and tax consequences. "
        "What should be researched?"
    )
    prompt = """
You are a Swiss legal researcher. Mandatory output language: English.
Jurisdiction assumption: use Swiss law and Canton of Geneva.
Research lens: posture is defense_audit_dispute, objective is balanced, scope is cross_border_multi_jurisdiction.
Assumed output format: client-ready legal memo.
Preserve these facts: French national domiciled in Geneva for 18 years dies in 2026 with a second wife, children, a French matrimonial property regime, a will, an inheritance pact, a Jersey trust, Swiss and Singapore bank accounts, foreign assets, interim protective measures, and tax consequences.
Answer the explicit question: What should be researched?
Use official sources, primary legislation, tax authority guidance, case law and stable URLs.
Source domains: fedlex.admin.ch, ge.ch, legifrance.gouv.fr, jerseylaw.je, iras.gov.sg.
Use citations [1], [2] and a final notes section.
Ask up to three clarifying questions if essential facts are missing.
Structure the output with premises, analysis, conclusions and notes.
Flag residual uncertainty.
"""

    paths = validate_mod.write_validation(question, prompt, tmp_path, language="en")
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))

    assert audit["status"] == "pass"
    assert audit["failed_checks"] == []
    assert audit["requires_phased_workflow"] is False
    assert audit["topic_flags"] == []


def test_validate_prompt_accepts_broad_matter_controls(tmp_path: Path) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_broad_complete", "validate_prompt.py"
    )
    question = (
        "A French national domiciled in Geneva for 18 years dies in 2026 with "
        "a second wife, children, a French matrimonial property regime, a will, "
        "an inheritance pact, a Jersey trust, Swiss and Singapore bank accounts, "
        "foreign assets, interim protective measures, and tax consequences. "
        "What should be researched?"
    )
    prompt = """
You are a Swiss legal research team. Mandatory output language: English.
Jurisdiction assumption: use Swiss law and Canton of Geneva.
Research lens: posture is defense_audit_dispute, objective is balanced, scope is cross_border_multi_jurisdiction.
Assumed output format: phased legal memo and final synthesis.
Preserve these facts: French national domiciled in Geneva for 18 years dies in 2026 with a second wife, children, a French matrimonial property regime, a will, an inheritance pact, a Jersey trust, Swiss and Singapore bank accounts, foreign assets, interim protective measures, and tax consequences.
Answer the explicit question: What should be researched?
Use official sources, primary legislation, tax authority guidance, case law and stable URLs.
Source domains: fedlex.admin.ch, ge.ch, legifrance.gouv.fr, jerseylaw.je, iras.gov.sg.
Use citations [1], [2] and a final notes section.
Ask up to three clarifying questions if essential facts are missing.
Structure the output with premises, analysis, conclusions and notes.
Flag residual uncertainty.
Use a phased workflow: Phase 0 source map and chronology, Phase 1 jurisdiction and applicable law, later phases for succession, trust, tax, and synthesis.
For every major conclusion assign high confidence, moderate confidence, or uncertain/practice-dependent.
Distinguish black-letter Swiss law, unsettled doctrine, cantonal practice, likely litigation strategy, and evidentiary dependency.
Do not invent any case, decision, citation, tax circular, treaty provision, authority, administrative practice, or professional commentary; if it cannot be verified, say verification was not possible.
Keep the trust section tightly scoped and do not overclaim jurisdiction over trustees or foreign banks.
For tax, separate confirmed law, likely administrative practice, treaty-dependent or fact-dependent points, and missing facts.
"""

    paths = validate_mod.write_validation(question, prompt, tmp_path, language="en")
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))

    assert audit["status"] == "pass"
    assert audit["failed_checks"] == []
    assert audit["requires_phased_workflow"] is False
    assert audit["topic_flags"] == []
    assert audit["source_domains"] == [
        "https://fedlex.admin.ch/",
        "https://ge.ch/",
        "https://legifrance.gouv.fr/",
        "https://jerseylaw.je/",
        "https://iras.gov.sg/",
    ]
    assert audit["source_domain_policy"] == "model_curated_only"
    assert "source_domains" in paths
    assert "source_domains_comma" in paths


def test_validate_prompt_flags_missing_requirements(tmp_path: Path) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_missing", "validate_prompt.py"
    )
    question = (
        "Alfa S.r.l. paid EUR 1,250,000 on 31/12/2025. "
        "What sources should be checked?"
    )
    prompt = "Please research this."

    paths = validate_mod.write_validation(question, prompt, tmp_path, language="en")
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))

    assert audit["status"] == "fail"
    assert "language_lock" in audit["failed_checks"]
    assert "source_requirements" in audit["failed_checks"]
    assert "jurisdiction_lock" in audit["failed_checks"]
    assert "research_lens" in audit["failed_checks"]
    assert "EUR 1,250,000" in audit["missing_fact_anchors"]
    assert audit["missing_explicit_questions"] == ["What sources should be checked?"]


def test_validate_prompt_requires_french_geneva_jurisdiction(
    tmp_path: Path,
) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_fr", "validate_prompt.py"
    )
    question = "Comment traiter une donation de CHF 20 000 en 2025?"
    prompt = """
Vous êtes avocat fiscaliste. Langue obligatoire: français.
Hypothèse de juridiction: nous utiliserons le droit suisse et le Canton de Genève.
Angle de recherche: posture assessment_ex_post, objectif balanced, portée domestic_only.
Format de sortie supposé: mémo juridique client-ready.
Préservez ces faits: donation de CHF 20 000 en 2025.
Question explicite: Comment traiter une donation de CHF 20 000 en 2025?
Utilisez des sources officielles, la législation primaire, la doctrine administrative, la jurisprudence et des URL stables.
Source domains: fedlex.admin.ch, ge.ch.
Utilisez les citations [1], [2] et une section finale de notes.
Posez jusqu'à trois questions de clarification si des faits essentiels manquent.
Structurez la réponse avec prémisses, analyse, conclusions et notes.
Signalez l'incertitude résiduelle et les points incertains.
"""

    paths = validate_mod.write_validation(question, prompt, tmp_path, language="fr")
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))

    assert audit["status"] == "pass"
    assert audit["checks"]["jurisdiction_lock"] is True
    assert audit["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"


def test_static_page_and_skill_match_plugin_contract() -> None:
    page = (ROOT / "static" / "shared" / "prompt-optimizer" / "index.html").read_text(
        encoding="utf-8"
    )
    skill = (PLUGIN_ROOT / "skills" / "prompt-optimizer" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for snippet in (
        "Optimize Prompt",
        "Ottimizza prompt",
        "One prompt to get started.",
        "Un solo prompt per iniziare.",
        "Un solo prompt para empezar.",
        "brief controllabile",
        "encargo revisable",
        "File prodotti",
        "Torna a Vera",
        "Back to Vera",
        "Volver a Vera",
        "question_inventory.json",
        "prompt_audit.json",
        "../vera/index.html",
        "/?lang=${safeLang}",
    ):
        assert snippet in page

    assert "must not make direct OpenAI API calls" in skill
    assert "must not choose governing law" in skill
    assert "must not use output language as a legal" in skill
    assert "angle_confirmation" in skill
    assert "jurisdiction_confirmation" in skill
    assert "options in chat and wait" in skill
    assert "choice in chat before drafting" in skill
    assert "continue in the same" in skill
    assert "Keep the improvement note local to chat or run artifacts." in skill
    assert "fill a form" in skill
    assert "Conversational Lawyer Intake" in skill
    assert "validate_prompt_optimizer_review" in skill
    assert "render_prompt_optimizer_review" in skill
    assert "ui://widget/prompt-optimizer-review.html" in skill
    assert "native Plan-mode choices" in skill


def test_mcp_review_server_validates_and_renders_prompt_payload() -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": "prompt-optimizer-test-run",
        "review_type": "prompt_optimizer_review",
        "item_count": 2,
        "items": [
            {
                "id": "artifact-1",
                "item_type": "prompt_artifact",
                "title": "Optimized prompt",
                "output_path": "optimized_prompt.md",
                "allowed_actions": ["accept", "edit", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "evidence": [],
                "data": {},
                "status": "needs_review",
            },
            {
                "id": "audit-check-1",
                "item_type": "audit_check",
                "title": "language_lock",
                "output_path": "prompt_audit.json",
                "allowed_actions": ["accept", "reject", "edit", "mark_unclear", "skip"],
                "recommended_action": "reject",
                "evidence": [{"kind": "prompt_audit_check", "status": "fail"}],
                "data": {},
                "status": "needs_review",
            },
        ],
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": "prompt-optimizer-test-run",
    }
    ui_decisions = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": "prompt-optimizer-test-run",
        "decisions": [],
        "status": "pending_review",
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": "prompt-optimizer-test-run",
        "outputs": [],
        "status": "written_pending_review",
    }

    tools = _call_mcp_server("tools/list")
    tool_names = {tool["name"] for tool in tools["tools"]}
    assert "validate_prompt_optimizer_review" in tool_names
    assert "render_prompt_optimizer_review" in tool_names

    validate_result = _call_mcp_server(
        "tools/call",
        {
            "name": "validate_prompt_optimizer_review",
            "arguments": {
                "review_payload": review_payload,
                "run_intake": run_intake,
                "ui_decisions": ui_decisions,
                "final_artifacts": final_artifacts,
            },
        },
    )
    validation = json.loads(validate_result["content"][0]["text"])
    assert validation["ok"] is True
    assert validation["item_count"] == 2

    render_result = _call_mcp_server(
        "tools/call",
        {
            "name": "render_prompt_optimizer_review",
            "arguments": {
                "review_payload": review_payload,
                "run_intake": run_intake,
                "ui_decisions": ui_decisions,
                "final_artifacts": final_artifacts,
            },
        },
    )
    rendered = json.loads(render_result["content"][0]["text"])
    assert rendered["widget_type"] == "prompt_optimizer_review"
    assert (
        render_result["_meta"]["openai/outputTemplate"]
        == "ui://widget/prompt-optimizer-review.html"
    )

    resources = _call_mcp_server("resources/list")
    assert any(
        resource["uri"] == "ui://widget/prompt-optimizer-review.html"
        for resource in resources["resources"]
    )
    widget = _call_mcp_server(
        "resources/read", {"uri": "ui://widget/prompt-optimizer-review.html"}
    )
    assert "Prompt Optimizer Review" in widget["contents"][0]["text"]


def test_mcp_prompt_optimizer_localizes_spanish_runtime_and_handoff(
    tmp_path: Path,
) -> None:
    review_payload = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": "prompt-optimizer-es",
        "language": "es-ES",
        "review_type": "prompt_optimizer_review",
        "item_count": 1,
        "items": [
            {
                "id": "artifact-1",
                "item_type": "review_artifact",
                "title": "Paquete del prompt",
                "output_path": "prompt_package.md",
                "allowed_actions": ["accept", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "status": "needs_review",
            }
        ],
    }
    run_intake = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": "prompt-optimizer-es",
        "language": "es",
        "output_dir": tmp_path.as_posix(),
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": "prompt-optimizer-es",
        "outputs": [],
        "caveats": [],
        "next_actions": [],
        "status": "written_pending_review",
    }
    decisions = [{"item_id": "artifact-1", "action": "accept"}]

    initialized = _call_mcp_server(
        "initialize",
        {"protocolVersion": "2024-11-05", "_meta": {"locale": "es-ES"}},
    )
    validated = _call_mcp_server(
        "tools/call",
        {
            "name": "validate_prompt_optimizer_review",
            "arguments": {"review_payload": review_payload},
        },
    )["structuredContent"]
    invalid = _call_mcp_server(
        "tools/call",
        {
            "name": "validate_prompt_optimizer_review",
            "arguments": {
                "review_payload": {**review_payload, "item_count": 2},
            },
        },
    )["structuredContent"]
    saved_without_output = _call_mcp_server(
        "tools/call",
        {
            "name": "save_prompt_optimizer_decisions",
            "arguments": {
                "review_payload": review_payload,
                "decisions": decisions,
            },
        },
    )["structuredContent"]
    applied_without_output = _call_mcp_server(
        "tools/call",
        {
            "name": "apply_prompt_optimizer_decisions",
            "arguments": {
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
                "decisions": decisions,
            },
        },
    )["structuredContent"]
    applied = _call_mcp_server(
        "tools/call",
        {
            "name": "apply_prompt_optimizer_decisions",
            "arguments": {
                "run_intake": run_intake,
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
                "decisions": decisions,
            },
        },
    )["structuredContent"]

    assert "Ejecute validate_prompt_optimizer_review" in initialized["instructions"]
    assert "son válidos" in validated["message"]
    assert "debe coincidir" in invalid["error"]
    assert "no se ha escrito ningún archivo" in saved_without_output["message"]
    assert "no se ha escrito ningún archivo" in applied_without_output["message"]
    assert "Se ha aplicado 1 decisión" in applied["message"]
    assert applied["final_artifacts"]["next_actions"] == [
        "Utilice final_artifacts.json como galería revisada de artefactos para la entrega."
    ]
    handoff = (tmp_path / "review_handoff.md").read_text(encoding="utf-8")
    assert "Entrega para revisión" in handoff
    assert "## Revisión en Codex" in handoff
    assert "<!-- review-contract: Review Handoff -->" in handoff
    assert "Validate the payload" not in handoff


def test_mcp_apply_refreshes_prompt_package_after_prompt_edit(
    tmp_path: Path,
) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_apply",
        "validate_prompt.py",
    )
    question = (
        "Italian company Alfa S.r.l. paid EUR 1,250,000 on 31/12/2025. "
        "What sources should be checked?"
    )
    original_prompt = """
You are a tax lawyer. Mandatory output language: English.
Jurisdiction assumption: use Italian law.
Research lens: posture is assessment_ex_post, objective is balanced, scope is domestic_plus_EU.
Assumed output format: client-ready legal memo.
Preserve these facts: Italian company Alfa S.r.l. paid EUR 1,250,000 on 31/12/2025.
Answer the explicit question: What sources should be checked?
Use official sources, primary legislation, tax authority guidance, case law and stable URLs.
Source domains: normattiva.it, agenziaentrate.gov.it, eur-lex.europa.eu.
Use citations [1], [2] and a final notes section.
Ask up to three clarifying questions if essential facts are missing.
Structure the output with premises, analysis, conclusions and notes.
Flag residual uncertainty.
"""
    edited_prompt = """
You are a senior tax lawyer. Mandatory output language: English.
Jurisdiction assumption: use Italian law.
Research lens: posture is assessment_ex_post, objective is balanced, scope is domestic_plus_EU.
Assumed output format: client-ready legal memo.
Preserve these facts: Italian company Alfa S.r.l. paid EUR 1,250,000 on 31/12/2025.
Answer the explicit question: What sources should be checked?
Use official sources, primary legislation, tax authority guidance, case law and stable URLs.
Source domains: normattiva.it, agenziaentrate.gov.it, eur-lex.europa.eu, oecd.org.
Use citations [1], [2] and a final notes section.
Ask up to three clarifying questions if essential facts are missing.
Structure the output with premises, analysis, conclusions and notes.
Flag residual uncertainty.
"""
    validate_mod.write_validation(question, original_prompt, tmp_path, language="en")
    run_intake = json.loads((tmp_path / "run_intake.json").read_text(encoding="utf-8"))
    review_payload = json.loads(
        (tmp_path / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (tmp_path / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (tmp_path / "final_artifacts.json").read_text(encoding="utf-8")
    )
    prompt_item = next(
        item
        for item in review_payload["items"]
        if item.get("output_path") == "optimized_prompt.md"
    )
    decisions = [
        {
            "item_id": item["id"],
            "action": "edit" if item["id"] == prompt_item["id"] else "accept",
            **(
                {"edit_value": edited_prompt} if item["id"] == prompt_item["id"] else {}
            ),
        }
        for item in review_payload["items"]
    ]

    save_result = _call_mcp_server(
        "tools/call",
        {
            "name": "save_prompt_optimizer_decisions",
            "arguments": {
                "run_intake": run_intake,
                "review_payload": review_payload,
                "ui_decisions": ui_decisions,
                "decisions": decisions,
            },
        },
    )
    saved = save_result["structuredContent"]
    assert saved["ok"] is True
    assert saved["decision_count"] == len(review_payload["items"])

    apply_result = _call_mcp_server(
        "tools/call",
        {
            "name": "apply_prompt_optimizer_decisions",
            "arguments": {
                "run_intake": run_intake,
                "review_payload": review_payload,
                "ui_decisions": ui_decisions,
                "final_artifacts": final_artifacts,
                "decisions": decisions,
            },
        },
    )
    applied_result = apply_result["structuredContent"]
    assert applied_result["ok"] is True
    assert applied_result["target_update_count"] == 1
    assert applied_result["application_status"] == "final_ready"
    assert applied_result["run_intake_path"] == str(tmp_path / "run_intake.json")
    assert "oecd.org" in (tmp_path / "optimized_prompt.md").read_text(encoding="utf-8")
    audit = json.loads((tmp_path / "prompt_audit.json").read_text(encoding="utf-8"))
    assert "https://oecd.org/" in audit["source_domains"]
    assert "https://oecd.org/" in (tmp_path / "prompt_package.md").read_text(
        encoding="utf-8"
    )
    assert "https://oecd.org/" in (tmp_path / "source_domains.txt").read_text(
        encoding="utf-8"
    )
    assert "https://oecd.org/" in (tmp_path / "source_domains_comma.txt").read_text(
        encoding="utf-8"
    )

    applied = json.loads((tmp_path / "applied_decisions.json").read_text())
    prompt_effect = next(
        effect
        for effect in applied["effects"]
        if effect["item_id"] == prompt_item["id"]
    )
    assert prompt_effect["artifact_update"] == "target_artifact_updated"
    assert prompt_effect["downstream_regeneration_status"] == "regenerated"
    assert prompt_effect["downstream_regenerated_paths"] == [
        "prompt_audit.json",
        "prompt_package.md",
        "source_domains.txt",
        "source_domains_comma.txt",
    ]

    final_after_apply = json.loads((tmp_path / "final_artifacts.json").read_text())
    assert final_after_apply["status"] == "final_ready"
    prompt_output = next(
        output
        for output in final_after_apply["outputs"]
        if output["path"] == "optimized_prompt.md"
    )
    assert prompt_output["status"] == "updated_from_review"
    assert prompt_output["required_text"] == [
        "You are a senior tax lawyer. Mandatory output language: English."
    ]
    package_output = next(
        output
        for output in final_after_apply["outputs"]
        if output["path"] == "prompt_package.md"
    )
    assert package_output["status"] == "updated_from_review"
    assert "https://oecd.org/" in package_output["required_text"]
    assert final_after_apply["review_application"]["downstream_regenerated_paths"] == [
        "prompt_audit.json",
        "prompt_package.md",
        "source_domains.txt",
        "source_domains_comma.txt",
    ]
    run_intake = json.loads((tmp_path / "run_intake.json").read_text())
    review_apply_steps = [
        step
        for step in run_intake["execution_trace"]
        if step["kind"] == "deterministic_review_apply"
    ]
    assert len(review_apply_steps) == 1
    assert {
        "applied_decisions.json",
        "final_artifacts.json",
        "optimized_prompt.md",
        "prompt_audit.json",
        "prompt_package.md",
        "source_domains.txt",
        "source_domains_comma.txt",
        "ui_decisions.json",
    } <= set(review_apply_steps[0]["outputs"])
    contract_report = validate_contract(
        tmp_path,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()
