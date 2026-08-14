from __future__ import annotations

import importlib.util
import hashlib
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


def _running_customer_output(
    tmp_path: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    ledger_path = ROOT / "plugins" / "studio-archive" / "scripts" / "client_ledger.py"
    module_name = "test_prompt_optimizer_customer_ledger"
    ledger = sys.modules.get(module_name)
    if ledger is None:
        spec = importlib.util.spec_from_file_location(module_name, ledger_path)
        assert spec is not None and spec.loader is not None
        ledger = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = ledger
        spec.loader.exec_module(ledger)
    client_root = tmp_path / "Managed Customer"
    client_root.mkdir()
    client_id = "client_111111111111111111111111"
    ledger.create_client_manifest(client_root, client_id)
    engagement = ledger.create_engagement(client_root, client_id, "Test engagement")
    source = tmp_path / "managed-source.txt"
    source.write_text("managed input\n", encoding="utf-8")
    imported = ledger.import_document(
        client_root,
        client_id,
        engagement["engagement_id"],
        source,
        "source",
    )
    prepared = ledger.prepare_run(
        client_root,
        client_id,
        engagement["engagement_id"],
        "prompt-optimizer",
        "test-version",
        input_ids=[imported["receipt"]["input_id"]],
    )
    running = ledger.start_run(
        client_root,
        engagement["engagement_id"],
        prepared["run"]["run_id"],
    )
    context = running["context"]
    return (
        Path(running["output_dir"]),
        Path(context["context_path"]),
        context,
    )


def _file_snapshot(root: Path) -> dict[str, bytes]:
    """Return the exact relative file content below a test root."""

    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _answer_contract(
    *,
    document_type: str = "client-ready legal memo",
    generation_route: str = "chatgpt_deep_research",
    question_domain: str = "tax",
    output_language: str = "English",
    jurisdiction: str = "Italian law",
) -> dict[str, str]:
    return {
        "schema_version": "1.0",
        "question_domain": question_domain,
        "generation_route": generation_route,
        "document_type": document_type,
        "purpose": "Answer the supplied professional question",
        "audience": "Professional reviewer",
        "output_language": output_language,
        "jurisdiction_status": "confirmed",
        "jurisdiction": jurisdiction,
        "evidence_display": "inline_citations",
        "validation_profile": "source_identity_support_reasoning_and_judgment",
        "validation_scope": "all_material_claims",
        "correction_policy": "correct_when_supported",
        "judgment_policy": "flag_for_professional_review",
    }


def _prompt_contract_review(
    *,
    attention_dimension: str | None = None,
    attention_status: str = "does_not_conform",
    reviewer_action: str | None = None,
) -> dict[str, Any]:
    dimensions = {
        dimension: {
            "status": (
                attention_status if dimension == attention_dimension else "conforms"
            ),
            "analysis": (
                "The optimized prompt conflicts with this contract dimension."
                if dimension == attention_dimension
                else "The optimized prompt semantically conforms."
            ),
        }
        for dimension in (
            "question_and_material_facts",
            "generation_route",
            "document_type",
            "purpose",
            "audience",
            "output_language",
            "jurisdiction",
            "evidence_display",
            "research_lens",
            "validation_policy",
            "source_strategy",
        )
    }
    return {
        "schema_version": "1.0",
        "review_method": "model_led_semantic_conformance_review",
        "dimensions": dimensions,
        "overall_status": "does_not_conform" if attention_dimension else "conforms",
        "reviewer_action": reviewer_action
        or ("edit" if attention_dimension else "accept"),
    }


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
    assert recipe["lens"] == {
        "posture": "unconfirmed",
        "objective": "unconfirmed",
        "scope": "unconfirmed",
    }
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
    assert recipe["lawyer_intake"]["mode"] == "model_led_ask_only_when_material"


def test_inspect_question_leaves_angle_and_confirmation_to_semantic_review(
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
    assert angle_confirmation["required"] is False
    assert angle_confirmation["mode"] == "model_led_confirmation_if_material"
    assert angle_confirmation["decision_owner"] == "codex_or_user"
    assert angle_confirmation["determination_status"] == (
        "not_determined_by_inspection"
    )
    assert angle_confirmation["options"] == []
    assert recipe["lawyer_intake"]["angle_confirmation_required"] is False

    assert recipe["jurisdiction_policy"]["default_jurisdiction"] == "unconfirmed"
    assert recipe["jurisdiction_policy"]["selection_status"] == "unconfirmed"
    jurisdiction_confirmation = recipe["jurisdiction_confirmation"]
    assert jurisdiction_confirmation["required"] is False
    assert jurisdiction_confirmation["mode"] == "model_led_confirmation_if_material"
    assert "national law" in jurisdiction_confirmation["reason"]
    jurisdiction_option_ids = {
        option["id"] for option in jurisdiction_confirmation["options"]
    }
    assert "eu_law_baseline" in jurisdiction_option_ids
    assert "eu_plus_member_state" in jurisdiction_option_ids
    assert recipe["lawyer_intake"]["jurisdiction_confirmation_required"] is False
    assert recipe["lawyer_intake"]["questions"] == []


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


def test_explicit_italian_law_does_not_force_confirmation() -> None:
    inspect_mod = load_script(
        "prompt_optimizer_explicit_italian_framework", "inspect_question.py"
    )
    inventory = inspect_mod.inspect_question_text(
        "Under Italian law, can Alfa S.r.l. terminate this agreement?"
    )
    policy = inspect_mod.jurisdiction_policy_for_question(
        "en", inventory.language_hint, inventory.jurisdiction_hints
    )

    confirmation = inspect_mod.jurisdiction_confirmation_for_question(inventory, policy)

    assert "Italy" in inventory.jurisdiction_hints
    assert confirmation["required"] is False
    assert confirmation["decision_owner"] == "codex_or_user"
    assert confirmation["preferred_option_id"] is None


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

    assert recipe["lens"]["posture"] == "unconfirmed"
    assert recipe["lens"]["objective"] == "unconfirmed"
    assert intake["mode"] == "model_led_ask_only_when_material"
    assert intake["max_questions"] == 3
    assert intake["questions"] == []
    assert intake["output_format_options"] == []
    assert "Do not ask the user whether to optimize" in intake["instruction"]


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
    (tmp_path / "draft_prompt.md").write_text(prompt, encoding="utf-8")
    (tmp_path / "draft_source_domains.txt").write_text(
        "normattiva.it\nagenziaentrate.gov.it\neur-lex.europa.eu\n",
        encoding="utf-8",
    )

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=_answer_contract(),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
    )
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
    assert audit["answer_contract"]["document_type"] == "client-ready legal memo"
    assert paths["answer_contract"] == tmp_path / "answer_contract.json"
    assert paths["prompt_contract_review"] == tmp_path / "prompt_contract_review.json"
    assert audit["prompt_contract_review_audit"]["status"] == "pass"
    assert "exact dates" in audit["assurance_boundary"]["mechanically_validated"]
    assert "question meaning" in audit["assurance_boundary"]["model_led"]
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
    assert "question_preview" not in review_payload["summary"]
    assert ui_decisions["status"] == "pending_review"
    assert ui_decisions["decision_count"] == 0
    assert final_artifacts["status"] == "written_pending_review"
    expected_review_hash = hashlib.sha256(
        (tmp_path / "review_payload.json").read_bytes()
    ).hexdigest()
    assert ui_decisions["review_payload_sha256"] == expected_review_hash
    assert final_artifacts["review_payload_sha256"] == expected_review_hash
    output_records = {output["path"]: output for output in final_artifacts["outputs"]}
    assert "draft_prompt.md" not in output_records
    assert "draft_source_domains.txt" not in output_records
    assert (
        output_records["prompt_audit.json"]["size_bytes"]
        == paths["prompt_audit"].stat().st_size
    )
    for output in output_records.values():
        if "size_bytes" in output:
            assert output["size_bytes"] == (tmp_path / output["path"]).stat().st_size
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
        "## Answer Contract",
        "## Model-Led Research Lens",
        "## Prompt-Contract Semantic Review",
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


def test_managed_prompt_writer_rejects_input_outside_run_without_writes(
    tmp_path: Path,
) -> None:
    output_dir, _context_path, context = _running_customer_output(tmp_path)
    validate_mod = load_script(
        "prompt_optimizer_validate_prompt_managed_input_escape",
        "validate_prompt.py",
    )
    outside_input = tmp_path / "outside-input.md"
    outside_input.write_text("outside\n", encoding="utf-8")
    before = _file_snapshot(tmp_path)

    with pytest.raises(ValueError, match="outside the current run"):
        validate_mod.write_validation(
            "What should be checked?",
            "Use official sources and cite every material claim.",
            output_dir,
            answer_contract=_answer_contract(),
            prompt_contract_review=_prompt_contract_review(),
            input_paths=[outside_input],
            client_engagement=context,
            client_run_id=str(context["run_id"]),
        )

    assert _file_snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "tool_name",
    ["save_prompt_optimizer_decisions", "apply_prompt_optimizer_decisions"],
)
@pytest.mark.parametrize(
    "output_ref_kind", ["escape", "stale_absolute", "missing_context"]
)
def test_mcp_managed_output_reference_is_rejected_without_writes(
    tmp_path: Path,
    tool_name: str,
    output_ref_kind: str,
) -> None:
    output_dir, context_path, context = _running_customer_output(tmp_path)
    old_client_root = Path(context["studio_client_folder"]["client_root"])
    if output_ref_kind == "stale_absolute":
        output_ref = output_dir.as_posix()
        renamed_client_root = tmp_path / "Renamed Customer"
        context_relative = context_path.relative_to(old_client_root)
        old_client_root.rename(renamed_client_root)
        context_path = renamed_client_root / context_relative
    elif output_ref_kind == "escape":
        output_ref = "../outside"
    else:
        output_ref = "outputs"
    run_id = str(context["run_id"])
    run_intake = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": run_id,
        "path_reference": "run_root_relative",
        "output_dir": output_ref,
    }
    review_payload = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": run_id,
        "review_type": "prompt_optimizer_review",
        "item_count": 1,
        "items": [
            {
                "id": "artifact-1",
                "item_type": "review_artifact",
                "title": "Prompt package",
                "output_path": "prompt_package.md",
                "allowed_actions": ["accept", "mark_unclear", "skip"],
                "recommended_action": "accept",
                "status": "needs_review",
            }
        ],
    }
    arguments: dict[str, Any] = {
        "run_intake": run_intake,
        "review_payload": review_payload,
        "decisions": [{"item_id": "artifact-1", "action": "accept"}],
    }
    if output_ref_kind != "missing_context":
        arguments["client_engagement"] = context_path.as_posix()
    if tool_name.startswith("apply_"):
        arguments["final_artifacts"] = {
            "schema_version": "1.0",
            "plugin": "prompt-optimizer",
            "workflow": "prompt-optimizer",
            "run_id": run_id,
            "outputs": [],
            "caveats": [],
            "next_actions": [],
            "status": "written_pending_review",
        }
    before = _file_snapshot(tmp_path)

    result = _call_mcp_server(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
    )

    assert result["isError"] is True
    assert result["structuredContent"]["ok"] is False
    assert _file_snapshot(tmp_path) == before
    assert not (tmp_path / "outside").exists()


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

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=_answer_contract(
            document_type="response strategy memo",
            jurisdiction="Swiss law and Canton of Geneva",
        ),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
    )
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
        answer_contract=_answer_contract(
            document_type="respuesta profesional",
            output_language="español",
            jurisdiction="Spanish law",
        ),
        prompt_contract_review=_prompt_contract_review(),
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
    client_run_id = "run_" + "b" * 24

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=_answer_contract(document_type="legal research brief"),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
        source_domains=[
            "https://www.normattiva.it/",
            "agenziaentrate.gov.it",
        ],
        client_run_id=client_run_id,
    )
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))
    run_intake = json.loads(paths["run_intake"].read_text(encoding="utf-8"))
    review_payload = json.loads(paths["review_payload"].read_text(encoding="utf-8"))

    assert run_intake["run_id"] == client_run_id
    assert review_payload["run_id"] == client_run_id
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


def test_validate_prompt_supports_direct_one_page_letter_contract(
    tmp_path: Path,
) -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_direct_letter",
        "validate_prompt.py",
    )
    question = (
        "Italian company Alfa S.r.l. received a payment demand on 31/12/2025. "
        "How should it respond?"
    )
    prompt = """
You are an Italian lawyer. Mandatory output language: English.
Jurisdiction assumption: use Italian law.
Research lens: posture is defense_audit_dispute, objective is balanced, scope is domestic_only.
Produce a one-page legal letter for the claimant explaining Alfa S.r.l.'s response.
Preserve these facts: Italian company Alfa S.r.l.; payment demand; 31/12/2025.
Answer the explicit question: How should it respond?
Use official sources, primary legislation, case law and stable URLs.
Maintain an internal source record for every material legal claim; do not show citations in the letter.
Ask up to three clarifying questions if essential facts are missing.
Flag residual uncertainty and avoid overstating judgment-dependent conclusions.
"""
    contract = _answer_contract(
        document_type="one-page legal letter",
        generation_route="codex_direct",
        question_domain="legal",
    )
    contract["evidence_display"] = "source_record_only"

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=contract,
        prompt_contract_review=_prompt_contract_review(),
        language="en",
        source_domains=["normattiva.it"],
    )
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))
    readme = paths["readme_human"].read_text(encoding="utf-8")

    assert audit["status"] == "pass"
    assert audit["checks"]["citation_rules"] is True
    assert audit["answer_contract"]["generation_route"] == "codex_direct"
    assert "Use `optimized_prompt.md` as the instructions" in readme
    assert "Paste `optimized_prompt.md` into Deep Research" not in readme


def test_validate_answer_contract_rejects_unresolved_required_shape() -> None:
    validate_mod = load_script(
        "prompt_optimizer_validate_answer_contract",
        "validate_prompt.py",
    )
    contract = _answer_contract()
    contract["generation_route"] = "keyword_classifier"
    contract["document_type"] = ""

    audit = validate_mod.validate_answer_contract(contract)

    assert audit["status"] == "fail"
    assert audit["missing_fields"] == ["document_type"]
    assert audit["invalid_fields"] == ["generation_route"]


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

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=_answer_contract(),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
    )
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

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=_answer_contract(
            document_type="phased legal memo and final synthesis",
            question_domain="mixed",
            jurisdiction="Swiss law and Canton of Geneva",
        ),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
    )
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

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=_answer_contract(),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
    )
    audit = json.loads(paths["prompt_audit"].read_text(encoding="utf-8"))

    assert audit["status"] == "fail"
    assert "language_lock" in audit["failed_checks"]
    assert "source_requirements" in audit["failed_checks"]
    assert "jurisdiction_lock" in audit["failed_checks"]
    assert "research_lens" in audit["failed_checks"]
    assert "EUR 1,250,000" in audit["missing_fact_anchors"]
    assert "Alfa S.r.l." in audit["missing_fact_anchors"]
    assert audit["missing_explicit_questions"] == ["What sources should be checked?"]
    assert "explicit_questions_preserved" not in audit["failed_checks"]
    assert audit["observations"]["literal_question_overlap_is_gating"] is False


def test_model_led_contract_review_blocks_wrong_jurisdiction_prompt() -> None:
    validate_mod = load_script(
        "prompt_optimizer_semantic_jurisdiction_boundary", "validate_prompt.py"
    )
    question = "Under French law, what limitation period applies to the claim?"
    prompt = """
You are a lawyer. Mandatory output language: English.
Legal framework: use French law.
Research lens: posture is assessment, objective is advice, scope is the claim.
Produce a client-ready legal memo.
Preserve the supplied facts and answer which limitation period governs.
Use official sources, legislation, case law, and stable URLs.
Use citations [1] and a final notes section.
Ask clarifying questions only if essential facts are missing.
Structure the output with analysis and conclusions, and flag uncertainty.
"""

    audit = validate_mod.validate_prompt_text(
        question,
        prompt,
        answer_contract=_answer_contract(jurisdiction="Italian law"),
        prompt_contract_review=_prompt_contract_review(
            attention_dimension="jurisdiction"
        ),
        language="en",
    )

    assert audit["answer_contract_audit"]["status"] == "pass"
    assert audit["checks"]["jurisdiction_lock"] is True
    assert audit["prompt_contract_review_audit"]["attention_dimensions"] == [
        "jurisdiction"
    ]
    assert audit["status"] == "fail"
    assert "prompt_contract_review" in audit["failed_checks"]


def test_semantic_review_allows_faithful_question_paraphrase() -> None:
    validate_mod = load_script(
        "prompt_optimizer_semantic_paraphrase_boundary", "validate_prompt.py"
    )
    question = "Under Italian law, what sources should be checked?"
    prompt = """
You are a lawyer. Mandatory output language: English.
Legal framework: use Italian law.
Research lens: posture is assessment, objective is advice, scope is Italian law.
Produce a client-ready legal memo.
Identify the authoritative materials needed to resolve the matter.
Use official sources, legislation, case law, and stable URLs.
Use citations [1] and a final notes section.
Ask clarifying questions only if essential facts are missing.
Structure the output with analysis and conclusions, and flag uncertainty.
"""

    audit = validate_mod.validate_prompt_text(
        question,
        prompt,
        answer_contract=_answer_contract(question_domain="legal"),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
    )

    assert audit["missing_explicit_questions"] == [
        "Under Italian law, what sources should be checked?"
    ]
    assert audit["observations"]["literal_explicit_questions_preserved"] is False
    assert audit["status"] == "pass"


def test_prompt_contract_evaluation_corpus_covers_material_boundaries() -> None:
    corpus = json.loads(
        (PLUGIN_ROOT / "evals" / "prompt_contract_cases.json").read_text(
            encoding="utf-8"
        )
    )
    case_ids = {case["id"] for case in corpus["cases"]}

    assert corpus["schema_version"] == "1.0"
    assert {
        "wrong-jurisdiction",
        "faithful-paraphrase",
        "omitted-legal-entity",
        "wrong-generation-route",
    } <= case_ids


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

    paths = validate_mod.write_validation(
        question,
        prompt,
        tmp_path,
        answer_contract=_answer_contract(
            document_type="mémo juridique client-ready",
            output_language="français",
            jurisdiction="Swiss law and Canton of Geneva",
        ),
        prompt_contract_review=_prompt_contract_review(),
        language="fr",
    )
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
        "question_inventory.json",
        "prompt_audit.json",
        "/?lang=${safeLang}",
    ):
        assert snippet in page

    assert "must not make direct OpenAI API calls" in skill
    assert "must not choose governing law" in skill
    assert "must not use output language as a legal" in skill
    assert "angle_confirmation" in skill
    assert "jurisdiction_confirmation" in skill
    assert "decision owner `codex_or_user`" in skill
    assert "generate fact-specific options" in skill
    assert "continue in the same" in skill
    assert "Keep the improvement note local to chat or run artifacts." in skill
    assert "fill a form" in skill
    assert "Conversational Lawyer Intake" in skill
    assert "validate_prompt_optimizer_review" in skill
    assert "render_prompt_optimizer_review" in skill
    assert "ui://widget/prompt-optimizer-review.html" in skill
    assert "native Plan-mode choices" in skill
    assert "draft_prompt_contract_review.json" in skill
    assert "--prompt-contract-review-file" in skill


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
    rendered = render_result["structuredContent"]
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
    output_dir, context_path, context = _running_customer_output(tmp_path)
    client_run_id = str(context["run_id"])
    review_payload = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": client_run_id,
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
        "run_id": client_run_id,
        "language": "es",
        "path_reference": "run_root_relative",
        "output_dir": "outputs",
    }
    final_artifacts = {
        "schema_version": "1.0",
        "plugin": "prompt-optimizer",
        "workflow": "prompt-optimizer",
        "run_id": client_run_id,
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
                "client_engagement": context_path.as_posix(),
                "review_payload": review_payload,
                "final_artifacts": final_artifacts,
                "decisions": decisions,
            },
        },
    )["structuredContent"]

    assert "Ejecute validate_prompt_optimizer_review" in initialized["instructions"]
    assert "es válida" in validated["message"]
    assert "debe coincidir" in invalid["error"]
    assert "no se ha escrito ningún archivo" in saved_without_output["message"]
    assert "no se ha escrito ningún archivo" in applied_without_output["message"]
    assert "Se ha aplicado 1 decisión" in applied["message"]
    assert applied["final_artifacts"]["next_actions"] == [
        "Utilice final_artifacts.json como galería revisada de artefactos para la entrega."
    ]
    handoff = (output_dir / "review_handoff.md").read_text(encoding="utf-8")
    assert "Entrega para revisión" in handoff
    assert "## Revisión en Codex" in handoff
    assert "<!-- review-contract: Review Handoff -->" in handoff
    assert "Validate the payload" not in handoff


def test_mcp_apply_refreshes_prompt_package_after_prompt_edit(
    tmp_path: Path,
) -> None:
    output_dir, context_path, context = _running_customer_output(tmp_path)
    client_run_id = str(context["run_id"])
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
    validate_mod.write_validation(
        question,
        original_prompt,
        output_dir,
        answer_contract=_answer_contract(),
        prompt_contract_review=_prompt_contract_review(),
        language="en",
        input_paths=[Path(context["input_bindings"][0]["path"])],
        client_engagement=context,
        client_run_id=client_run_id,
    )
    run_intake = json.loads(
        (output_dir / "run_intake.json").read_text(encoding="utf-8")
    )
    review_payload = json.loads(
        (output_dir / "review_payload.json").read_text(encoding="utf-8")
    )
    ui_decisions = json.loads(
        (output_dir / "ui_decisions.json").read_text(encoding="utf-8")
    )
    final_artifacts = json.loads(
        (output_dir / "final_artifacts.json").read_text(encoding="utf-8")
    )
    review_reference = {
        "path": "review_payload.json",
        "run_id": client_run_id,
        "review_payload_sha256": final_artifacts["review_payload_sha256"],
    }
    audit_before_move = json.loads(
        (output_dir / "prompt_audit.json").read_text(encoding="utf-8")
    )
    old_client_root = Path(context["studio_client_folder"]["client_root"])
    assert run_intake["path_reference"] == "run_root_relative"
    assert run_intake["output_dir"] == "outputs"
    assert all(not Path(value).is_absolute() for value in run_intake["input_paths"])
    assert all(
        not Path(value).is_absolute()
        for key, value in audit_before_move["review_session"].items()
        if key.endswith("_path")
    )
    assert all(
        old_client_root.as_posix() not in path.read_text(encoding="utf-8")
        for path in output_dir.glob("*.json")
    )
    renamed_client_root = tmp_path / "Renamed Customer"
    context_relative = context_path.relative_to(old_client_root)
    output_relative = output_dir.relative_to(old_client_root)
    old_client_root.rename(renamed_client_root)
    context_path = renamed_client_root / context_relative
    output_dir = renamed_client_root / output_relative
    assert not old_client_root.exists()
    validate_result = _call_mcp_server(
        "tools/call",
        {
            "name": "validate_prompt_optimizer_review",
            "arguments": {
                "run_intake": run_intake,
                "client_engagement": context_path.as_posix(),
                "review_reference": review_reference,
            },
        },
    )
    validated = validate_result["structuredContent"]
    assert "review_payload" not in validated
    assert validated["review_reference"]["review_payload_sha256"] == (
        review_reference["review_payload_sha256"]
    )
    assert len(validated["review_reference"]["persistence_token"]) == 43
    assert original_prompt.strip() not in validate_result["content"][0]["text"]
    render_result = _call_mcp_server(
        "tools/call",
        {
            "name": "render_prompt_optimizer_review",
            "arguments": {
                "run_intake": run_intake,
                "client_engagement": context_path.as_posix(),
                "review_reference": review_reference,
            },
        },
    )
    assert render_result["structuredContent"]["review_payload"] == review_payload
    assert len(render_result["structuredContent"]["persistence_token"]) == 43
    widget = _call_mcp_server(
        "resources/read", {"uri": "ui://widget/prompt-optimizer-review.html"}
    )
    assert "persistence_token" in widget["contents"][0]["text"]
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
                "client_engagement": context_path.as_posix(),
                "review_reference": review_reference,
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
                "client_engagement": context_path.as_posix(),
                "review_reference": review_reference,
                "decisions": decisions,
            },
        },
    )
    applied_result = apply_result["structuredContent"]
    assert applied_result["ok"] is True, applied_result
    assert applied_result["target_update_count"] == 1
    assert applied_result["application_status"] == "partial_review_applied"
    assert applied_result["run_intake_path"] == str(output_dir / "run_intake.json")
    assert "oecd.org" in (output_dir / "optimized_prompt.md").read_text(
        encoding="utf-8"
    )
    audit = json.loads((output_dir / "prompt_audit.json").read_text(encoding="utf-8"))
    assert "https://oecd.org/" in audit["source_domains"]
    assert audit["status"] == "fail"
    assert audit["prompt_contract_review_audit"]["attention_dimensions"] == [
        "question_and_material_facts",
        "generation_route",
        "document_type",
        "purpose",
        "audience",
        "output_language",
        "jurisdiction",
        "evidence_display",
        "research_lens",
        "validation_policy",
        "source_strategy",
    ]
    semantic_review = json.loads(
        (output_dir / "prompt_contract_review.json").read_text(encoding="utf-8")
    )
    assert semantic_review["overall_status"] == "not_reviewed"
    assert semantic_review["stale_reason"] == "optimized_prompt_edited_after_review"
    assert "https://oecd.org/" in (output_dir / "prompt_package.md").read_text(
        encoding="utf-8"
    )
    assert "https://oecd.org/" in (output_dir / "source_domains.txt").read_text(
        encoding="utf-8"
    )
    assert "https://oecd.org/" in (output_dir / "source_domains_comma.txt").read_text(
        encoding="utf-8"
    )

    applied = json.loads((output_dir / "applied_decisions.json").read_text())
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
        "prompt_contract_review.json",
    ]

    final_after_apply = json.loads((output_dir / "final_artifacts.json").read_text())
    assert final_after_apply["status"] == "partial_review_applied"
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
        "prompt_contract_review.json",
    ]
    assert any(
        "semantic review" in action for action in final_after_apply["next_actions"]
    )
    run_intake = json.loads((output_dir / "run_intake.json").read_text())
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
        "prompt_contract_review.json",
        "source_domains.txt",
        "source_domains_comma.txt",
        "ui_decisions.json",
    } <= set(review_apply_steps[0]["outputs"])
    contract_report = validate_contract(
        output_dir,
        strict_data_posture=True,
        strict_execution_trace=True,
        strict_output_paths=True,
        strict_output_content=True,
    )
    assert contract_report.ok, contract_report.as_dict()
